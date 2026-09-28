#!/usr/bin/env python3
"""Build an SFT dataset from verified software-reconstruction trajectories.

The source trajectories are never modified.  This exporter:

* uses the corrected Qwen-Max pass pool plus the raw v6/v7 pass lists;
* follows every safe ``continued_trajectory_ref``;
* canonicalizes recoverable agent JSON and masks malformed agent messages;
* removes only exact duplicate turns and post-solution read-only tails from
  timeout/cancelled/regraded passes;
* adds a generic, explicitly marked completion turn when Harbor did not finish;
* compacts terminal observations and splits long conversations into windows;
* emits source/repair provenance and task-balanced weights.

All generated data must be written outside the source repository.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterable


SOURCE_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(
    os.environ.get(
        "SWR_DATA_ROOT",
        "/path/to/software_reconstruction_data",
    )
)
QMAX_POOL = Path(
    os.environ.get(
        "SWR_QMAX_POOL",
        str(
            DATA_ROOT
            / "qwen38_corrected_pass_pool_20260904_v5_openscad_geometry"
            / "corrected_pass_pool.jsonl"
        ),
    )
)
Q27_ROOT = Path(
    os.environ.get(
        "SWR_Q27_ROLLOUT_ROOT",
        "/path/to/software_reconstruction_runs/"
        "software_reconstruction/qwen38_27b_corrected3000_3nodes_20260905",
    )
)
V6_ROOT = Path(
    os.environ.get(
        "SWR_Q27_V6_ROOT",
        str(Q27_ROOT / "production_v6_full3000_contextguard_t1h_20260905_2240"),
    )
)
V7_ROOT = Path(
    os.environ.get(
        "SWR_Q27_V7_ROOT",
        str(Q27_ROOT / "production_v7_reflectrepair_t2h_mt500_20260906_133829"),
    )
)

EXPECTED_SOURCE_COUNTS = {
    "qwen38_max": 748,
    "qwen38_27b_v6": 475,
    "qwen38_27b_v7": 199,
}
SHARD_PREFIX_RE = re.compile(r"^\d+__shard\d+__")
ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
BLANK_LINES_RE = re.compile(r"\n{4,}")
SECRET_PATTERNS = (
    (re.compile(r"\bdtn_[A-Za-z0-9]{20,}\b"), "[REDACTED_DAYTONA_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
)
SUCCESS_PATTERNS = (
    re.compile(r'"public_passed"\s*:\s*true', re.IGNORECASE),
    re.compile(r"\ball public (?:scenarios|checks).{0,40}\bpass", re.IGNORECASE),
    re.compile(r"\ball checks passed\b", re.IGNORECASE),
)
CONFIRMATION_PATTERNS = (
    re.compile(r"are you sure you want to mark the task as complete", re.IGNORECASE),
    re.compile(r'include\s+"task_complete"\s*:\s*true.+again', re.IGNORECASE | re.DOTALL),
)
MUTATION_PATTERNS = (
    re.compile(r"(?:^|[;&|]\s*)(?:rm|mv|cp|mkdir|touch|chmod|chown|ln|install)\b", re.MULTILINE),
    re.compile(r"\bsed\s+-[^\n]*i\b"),
    re.compile(r"\bperl\s+-[^\n]*i\b"),
    re.compile(r"\b(?:apply_patch|git\s+apply|patch\s+-p\d*)\b"),
    re.compile(r"\b(?:make|cmake\s+--build|ninja|cargo\s+build|go\s+build)\b"),
    re.compile(r"\b(?:truncate|rsync|dd\b[^\n]*\bof=)\b"),
    re.compile(r"\b(?:curl|wget)\b[^\n]*(?:\s-o\s|\s-O\s)"),
    re.compile(r"\btar\b[^\n]*(?:\s-C\s+/(?:app/workspace|workspace)\b|--extract)"),
    re.compile(r"\b(?:write_text|write_bytes|writelines|os\.remove|os\.unlink|os\.rename|shutil\.)\b"),
    re.compile(r"\bopen\s*\([^)]*,\s*['\"][wa+x]"),
    re.compile(r"\b(?:cat|tee|echo|printf)\b[^\n]*>{1,2}\s*(?!&)", re.MULTILINE),
    re.compile(r"(?<!\d)>{1,2}\s*/(?:app/workspace|workspace)(?:/|\b)"),
)
IGNORABLE_SYSTEM_KEYS = {"subagent_trajectory_ref"}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def normalize_task(task: str) -> str:
    return SHARD_PREFIX_RE.sub("", Path(task).name)


def json_load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def exception_type(result: dict[str, Any]) -> str:
    info = result.get("exception_info")
    if isinstance(info, dict):
        value = info.get("exception_type")
        if value:
            return str(value)
    return "none"


@dataclasses.dataclass(frozen=True)
class SourceRecord:
    trajectory_id: str
    source_rollout: str
    source_run: str
    task: str
    trial_name: str
    trial_dir: str
    result_path: str
    artifacts_workspace: str | None
    family: str | None
    outcome_origin: str
    old_reward: float | None
    corrected_reward: float
    exception_type: str
    n_input_tokens: int
    n_output_tokens: int
    n_episodes_metadata: int


def make_trajectory_id(source_rollout: str, trial_dir: str) -> str:
    digest = hashlib.sha1(f"{source_rollout}\0{trial_dir}".encode()).hexdigest()[:16]
    return f"{source_rollout}__{digest}"


def record_from_qmax(row: dict[str, Any]) -> SourceRecord:
    trial_dir = Path(str(row["trial_dir"]))
    result_path = Path(str(row.get("original_result_path") or trial_dir / "result.json"))
    result = json_load(result_path)
    agent = result.get("agent_result") or {}
    metadata = agent.get("metadata") or {}
    old_reward = row.get("old_reward")
    return SourceRecord(
        trajectory_id=make_trajectory_id("qwen38_max", str(trial_dir)),
        source_rollout="qwen38_max",
        source_run=str(row.get("source_run") or trial_dir.parent.name),
        task=normalize_task(str(row["task_id"])),
        trial_name=str(row.get("trial_name") or trial_dir.name),
        trial_dir=str(trial_dir),
        result_path=str(result_path),
        artifacts_workspace=str(row.get("artifacts_workspace") or row.get("workspace") or "") or None,
        family=str(row["family"]) if row.get("family") else None,
        outcome_origin=str(row.get("outcome_origin") or "corrected_pass_pool"),
        old_reward=float(old_reward) if old_reward is not None else None,
        corrected_reward=1.0,
        exception_type=exception_type(result),
        n_input_tokens=int(agent.get("n_input_tokens") or 0),
        n_output_tokens=int(agent.get("n_output_tokens") or 0),
        n_episodes_metadata=int(metadata.get("n_episodes") or 0),
    )


def aggregate_pass_names(run_dir: Path) -> list[str]:
    aggregate = json_load(run_dir / "result.json")
    evals = ((aggregate.get("stats") or {}).get("evals") or {})
    if not evals:
        raise ValueError(f"aggregate result has no evals: {run_dir}")
    evaluation = next(iter(evals.values()))
    rewards = ((evaluation.get("reward_stats") or {}).get("reward") or {})
    return [str(name) for name in rewards.get("1.0", [])]


def family_from_task_path(task_path: Path) -> str | None:
    variant_path = task_path / "tests" / "private" / "variant.json"
    if not variant_path.is_file():
        return None
    try:
        variant = json_load(variant_path)
    except Exception:
        return None
    value = variant.get("family_id") or variant.get("family")
    return str(value) if value else None


def records_from_q27(
    *,
    source_rollout: str,
    root: Path,
    run_prefix: str,
) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for node in range(3):
        run_dir = root / f"{run_prefix}{node}-round1"
        for trial_name in aggregate_pass_names(run_dir):
            trial_dir = run_dir / trial_name
            result_path = trial_dir / "result.json"
            result = json_load(result_path)
            task_id = result.get("task_id") or {}
            task_path_value = task_id.get("path") if isinstance(task_id, dict) else task_id
            task_path = Path(str(task_path_value)) if task_path_value else Path(str(result.get("task_name") or trial_name))
            agent = result.get("agent_result") or {}
            metadata = agent.get("metadata") or {}
            workspace = trial_dir / "artifacts" / "workspace"
            records.append(
                SourceRecord(
                    trajectory_id=make_trajectory_id(source_rollout, str(trial_dir)),
                    source_rollout=source_rollout,
                    source_run=run_dir.name,
                    task=normalize_task(task_path.name),
                    trial_name=trial_name,
                    trial_dir=str(trial_dir),
                    result_path=str(result_path),
                    artifacts_workspace=str(workspace) if workspace.exists() else None,
                    family=family_from_task_path(task_path),
                    outcome_origin="raw_reward",
                    old_reward=1.0,
                    corrected_reward=1.0,
                    exception_type=exception_type(result),
                    n_input_tokens=int(agent.get("n_input_tokens") or 0),
                    n_output_tokens=int(agent.get("n_output_tokens") or 0),
                    n_episodes_metadata=int(metadata.get("n_episodes") or 0),
                )
            )
    return records


def load_source_records() -> list[SourceRecord]:
    records: list[SourceRecord] = []
    with QMAX_POOL.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(record_from_qmax(json.loads(line)))
    records.extend(
        records_from_q27(
            source_rollout="qwen38_27b_v6",
            root=V6_ROOT,
            run_prefix="software-reconstruction-qwen38-27b-corrected3000-v6-contextguard-t1h-c100-node",
        )
    )
    records.extend(
        records_from_q27(
            source_rollout="qwen38_27b_v7",
            root=V7_ROOT,
            run_prefix="qwen35-synth832-6nodes-temp0_2-c100-node",
        )
    )
    records.sort(key=lambda item: (item.source_rollout, item.task, item.source_run, item.trial_name))
    return records


def load_chain(trial_dir: Path, max_segments: int = 200) -> tuple[list[tuple[Path, dict[str, Any]]], dict[str, Any]]:
    agent_dir = (trial_dir / "agent").resolve()
    current = agent_dir / "trajectory.json"
    seen: set[Path] = set()
    documents: list[tuple[Path, dict[str, Any]]] = []
    total_bytes = 0
    error: str | None = None

    for _ in range(max_segments):
        try:
            current = current.resolve()
            current.relative_to(agent_dir)
        except (OSError, ValueError):
            error = f"unsafe continuation path: {current}"
            break
        if current in seen:
            error = f"continuation cycle: {current}"
            break
        seen.add(current)
        try:
            document = json_load(current)
        except Exception as exc:
            error = f"unreadable segment {current}: {type(exc).__name__}: {exc}"
            break
        total_bytes += current.stat().st_size
        documents.append((current, document))
        reference = document.get("continued_trajectory_ref")
        if not reference:
            break
        if not isinstance(reference, str) or not reference.strip():
            error = f"invalid continuation reference in {current}"
            break
        current = current.parent / reference
    else:
        error = f"continuation chain exceeds {max_segments} segments"

    complete = bool(documents) and error is None and not documents[-1][1].get("continued_trajectory_ref")
    return documents, {
        "segments": len(documents),
        "bytes": total_bytes,
        "complete": complete,
        "error": error,
        "paths": [str(path) for path, _ in documents],
    }


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern, replacement in SECRET_PATTERNS:
        text, replacements = pattern.subn(replacement, text)
        count += replacements
    return text, count


def clean_text(text: str, *, max_chars: int | None = None) -> tuple[str, int, bool]:
    text = ANSI_RE.sub("", text.replace("\x00", ""))
    text, redactions = redact(text)
    text = BLANK_LINES_RE.sub("\n\n\n", text).strip()
    truncated = False
    if max_chars is not None and len(text) > max_chars:
        head_chars = max_chars // 3
        tail_chars = max_chars - head_chars
        removed = len(text) - max_chars
        text = (
            text[:head_chars]
            + f"\n\n[... {removed} characters deterministically omitted ...]\n\n"
            + text[-tail_chars:]
        )
        truncated = True
    return text, redactions, truncated


def serialize_observation(observation: Any) -> str:
    if observation is None:
        return ""
    if isinstance(observation, str):
        return observation
    if isinstance(observation, dict):
        results = observation.get("results")
        if isinstance(results, list):
            parts: list[str] = []
            for result in results:
                if isinstance(result, dict):
                    content = result.get("content")
                    if isinstance(content, str):
                        parts.append(content)
                    elif content is not None:
                        parts.append(json.dumps(content, ensure_ascii=False))
                elif result is not None:
                    parts.append(str(result))
            return "\n".join(parts)
    return json.dumps(observation, ensure_ascii=False)


def compact_observation(observation: Any, max_chars: int) -> tuple[str, dict[str, int]]:
    text = serialize_observation(observation)
    if "New Terminal Output:" in text:
        prefix, _, suffix = text.partition("New Terminal Output:")
        warnings = ""
        if "WARNINGS:" in prefix:
            warnings = prefix[prefix.index("WARNINGS:") :].strip() + "\n\n"
        text = warnings + "New Terminal Output:\n" + suffix.lstrip()
    cleaned, redactions, truncated = clean_text(text, max_chars=max_chars)
    return cleaned, {
        "secret_redactions": redactions,
        "truncated_observations": int(truncated),
    }


def extract_agent_payload(message: str) -> dict[str, Any] | None:
    stripped = message.strip()
    candidates: list[dict[str, Any]] = []
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            candidates.append(value)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        try:
            value, _ = decoder.raw_decode(stripped[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(value)

    for value in reversed(candidates):
        if isinstance(value.get("commands"), list):
            return value
    return None


def valid_agent_payload(payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    if not isinstance(payload.get("analysis"), str) or not isinstance(payload.get("plan"), str):
        return False
    commands = payload.get("commands")
    if not isinstance(commands, list):
        return False
    return all(isinstance(command, dict) and isinstance(command.get("keystrokes"), str) for command in commands)


def canonical_agent_message(message: str, *, copied: bool) -> tuple[str, dict[str, Any] | None, bool, int]:
    payload = extract_agent_payload(message)
    valid = valid_agent_payload(payload)
    if valid:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=False)
        canonical, redactions = redact(canonical)
        return canonical, payload, True, redactions
    cleaned, redactions, _ = clean_text(message, max_chars=48_000 if copied else None)
    return cleaned, payload, False, redactions


def text_is_mutating(text: str) -> bool:
    scrubbed = re.sub(r"\d*>\s*&\d+", "", text)
    scrubbed = re.sub(r"\d*>\s*/dev/null", "", scrubbed)
    return any(pattern.search(scrubbed) for pattern in MUTATION_PATTERNS)


def command_is_mutating(payload: dict[str, Any] | None, raw_message: str) -> bool:
    # A malformed response cannot be proven read-only, so it must remain in any
    # repaired timeout tail. This is deliberately conservative.
    if not valid_agent_payload(payload):
        return True
    commands = payload.get("commands")
    if isinstance(commands, list):
        for command in commands:
            if isinstance(command, dict) and isinstance(command.get("keystrokes"), str):
                if text_is_mutating(command["keystrokes"]):
                    return True
    # Also inspect the full response so recoverable wrappers/heredocs cannot
    # hide a workspace write from the command-only scan.
    return text_is_mutating(raw_message)


def observation_is_success(text: str) -> bool:
    return any(pattern.search(text) for pattern in SUCCESS_PATTERNS)


def observation_requests_confirmation(text: str) -> bool:
    return any(pattern.search(text) for pattern in CONFIRMATION_PATTERNS)


@dataclasses.dataclass
class ContextMessage:
    role: str
    content: str
    step_loss_mask: int = 0


@dataclasses.dataclass
class Event:
    content: str
    observation: str
    leading: list[ContextMessage]
    trainable: bool
    valid_payload: bool
    payload: dict[str, Any] | None
    copied: bool
    mutating: bool
    successful_observation: bool
    confirmation_observation: bool
    source_path: str
    source_step_id: Any
    synthetic: bool = False

    @property
    def task_complete(self) -> bool:
        return bool(self.payload and self.payload.get("task_complete") is True)


@dataclasses.dataclass
class Segment:
    source_path: str
    preamble: list[ContextMessage]
    events: list[Event]


def context_message_from_step(step: dict[str, Any], *, copied: bool) -> tuple[ContextMessage | None, int]:
    message = step.get("message")
    if not isinstance(message, str) or not message.strip():
        return None, 0
    source = step.get("source")
    if source == "agent":
        content, _, _, redactions = canonical_agent_message(message, copied=copied)
        return ContextMessage(role="assistant", content=content, step_loss_mask=0), redactions
    role = "user" if source in {"user", "system"} else "user"
    content, redactions, _ = clean_text(message, max_chars=64_000)
    return ContextMessage(role=role, content=content, step_loss_mask=0), redactions


def document_to_segment(
    path: Path,
    document: dict[str, Any],
    *,
    max_observation_chars: int,
) -> tuple[Segment, Counter[str]]:
    stats: Counter[str] = Counter()
    preamble: list[ContextMessage] = []
    pending: list[ContextMessage] = []
    events: list[Event] = []
    seen_live_agent = False

    steps = document.get("steps")
    if not isinstance(steps, list):
        steps = []
    for step in steps:
        if not isinstance(step, dict):
            stats["non_object_steps"] += 1
            continue
        copied = bool(step.get("is_copied_context"))
        source = step.get("source")
        if source == "system":
            observation = step.get("observation")
            results = observation.get("results") if isinstance(observation, dict) else None
            if isinstance(results, list) and any(
                isinstance(result, dict) and IGNORABLE_SYSTEM_KEYS.intersection(result)
                for result in results
            ):
                stats["summarization_handoff_steps_omitted"] += 1
                continue

        if source == "agent" and not copied:
            seen_live_agent = True
            raw_message = step.get("message")
            if not isinstance(raw_message, str) or not raw_message.strip():
                stats["empty_agent_steps"] += 1
                continue
            content, payload, valid, redactions = canonical_agent_message(raw_message, copied=False)
            observation, obs_stats = compact_observation(step.get("observation"), max_observation_chars)
            stats.update(obs_stats)
            stats["secret_redactions"] += redactions
            if valid:
                stats["valid_agent_payloads"] += 1
            else:
                stats["malformed_agent_payloads_masked"] += 1
            events.append(
                Event(
                    content=content,
                    observation=observation,
                    leading=pending,
                    trainable=valid,
                    valid_payload=valid,
                    payload=payload,
                    copied=False,
                    mutating=command_is_mutating(payload, raw_message),
                    successful_observation=observation_is_success(observation),
                    confirmation_observation=observation_requests_confirmation(observation),
                    source_path=str(path),
                    source_step_id=step.get("step_id"),
                )
            )
            pending = []
            continue

        context, redactions = context_message_from_step(step, copied=copied)
        stats["secret_redactions"] += redactions
        if context is None:
            continue
        target = pending if seen_live_agent else preamble
        target.append(context)
        if source == "agent" and copied:
            observation, obs_stats = compact_observation(step.get("observation"), max_observation_chars)
            stats.update(obs_stats)
            if observation:
                target.append(ContextMessage(role="user", content=observation, step_loss_mask=0))
            stats["copied_agent_context_steps"] += 1
        elif copied:
            stats["copied_context_steps"] += 1

    if pending:
        stats["trailing_context_messages_omitted"] += len(pending)
    return Segment(source_path=str(path), preamble=preamble, events=events), stats


def remove_exact_duplicate_events(segment: Segment) -> int:
    if len(segment.events) < 2:
        return 0
    kept: list[Event] = []
    removed = 0
    for event in segment.events:
        if (
            kept
            and not event.leading
            and event.content == kept[-1].content
            and event.observation == kept[-1].observation
        ):
            removed += 1
            continue
        kept.append(event)
    segment.events = kept
    return removed


def tail_repair_needed(record: SourceRecord) -> bool:
    return (
        record.exception_type != "none"
        or record.old_reward == 0.0
        or record.outcome_origin not in {"original_reward", "raw_reward"}
    )


def repair_final_tail(segment: Segment, record: SourceRecord) -> tuple[int, dict[str, Any]]:
    events = segment.events
    details: dict[str, Any] = {
        "tail_repair_requested": tail_repair_needed(record),
        "last_mutating_event": None,
        "anchor_event": None,
    }
    if not events or not tail_repair_needed(record):
        return 0, details

    last_mutating = max((index for index, event in enumerate(events) if event.mutating), default=-1)
    anchor = last_mutating
    for index, event in enumerate(events):
        if index < last_mutating:
            continue
        if event.successful_observation or event.task_complete:
            anchor = max(anchor, index)
    details["last_mutating_event"] = last_mutating if last_mutating >= 0 else None
    details["anchor_event"] = anchor if anchor >= 0 else None

    if anchor < 0 or anchor >= len(events) - 1:
        return 0, details
    removed = len(events) - anchor - 1
    segment.events = events[: anchor + 1]
    return removed, details


def synthetic_completion_event(source_path: str) -> Event:
    payload = {
        "analysis": "The implementation and required deliverables are complete.",
        "plan": "Submit the completed workspace for grading.",
        "commands": [],
        "task_complete": True,
    }
    return Event(
        content=json.dumps(payload, ensure_ascii=False),
        observation="",
        leading=[],
        trainable=True,
        valid_payload=True,
        payload=payload,
        copied=False,
        mutating=False,
        successful_observation=False,
        confirmation_observation=False,
        source_path=source_path,
        source_step_id="synthetic_completion",
        synthetic=True,
    )


def ensure_completion(segment: Segment) -> tuple[bool, str]:
    if not segment.events:
        segment.events.append(synthetic_completion_event(segment.source_path))
        return True, "empty_final_segment"
    final = segment.events[-1]
    if final.task_complete and not final.confirmation_observation:
        return False, "existing_accepted_completion"
    segment.events.append(synthetic_completion_event(segment.source_path))
    if final.task_complete and final.confirmation_observation:
        return True, "second_confirmation"
    return True, "missing_completion"


def append_message(messages: list[dict[str, Any]], message: ContextMessage) -> None:
    if not message.content.strip():
        return
    item = {
        "role": message.role,
        "content": message.content,
        "step_loss_mask": int(message.step_loss_mask),
    }
    if messages and messages[-1]["role"] == item["role"] == "user":
        messages[-1]["content"] += "\n\n" + item["content"]
        return
    if messages and messages[-1]["role"] == item["role"] == "assistant":
        messages.append(
            {
                "role": "user",
                "content": "[No additional terminal output was recorded.]",
                "step_loss_mask": 0,
            }
        )
    messages.append(item)


def messages_for_events(
    preamble: list[ContextMessage],
    events: list[Event],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for context in preamble:
        append_message(messages, context)
    for index, event in enumerate(events):
        for context in event.leading:
            append_message(messages, context)
        append_message(
            messages,
            ContextMessage(
                role="assistant",
                content=event.content,
                step_loss_mask=1 if event.trainable else 0,
            ),
        )
        if index < len(events) - 1 and event.observation:
            append_message(
                messages,
                ContextMessage(role="user", content=event.observation, step_loss_mask=0),
            )
    return messages


def first_user_message(preamble: list[ContextMessage]) -> ContextMessage:
    for message in preamble:
        if message.role == "user" and message.content.strip():
            return ContextMessage(role="user", content=message.content, step_loss_mask=0)
    return ContextMessage(
        role="user",
        content="Continue solving the current terminal task from the recorded state.",
        step_loss_mask=0,
    )


def continuation_preamble(segment: Segment, previous: Event) -> list[ContextMessage]:
    preamble = [first_user_message(segment.preamble)]
    preamble.append(ContextMessage(role="assistant", content=previous.content, step_loss_mask=0))
    if previous.observation:
        preamble.append(ContextMessage(role="user", content=previous.observation, step_loss_mask=0))
    return preamble


def total_message_chars(messages: Iterable[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content") or "")) for message in messages)


def split_segment_windows(
    segment: Segment,
    max_conversation_chars: int,
) -> tuple[list[list[dict[str, Any]]], int]:
    if not segment.events:
        return [], 0
    windows: list[list[dict[str, Any]]] = []
    current: list[Event] = []
    current_preamble = segment.preamble
    oversized = 0

    for event in segment.events:
        candidate = current + [event]
        messages = messages_for_events(current_preamble, candidate)
        if current and total_message_chars(messages) > max_conversation_chars:
            complete = messages_for_events(current_preamble, current)
            windows.append(complete)
            previous = current[-1]
            current_preamble = continuation_preamble(segment, previous)
            current = [event]
        else:
            current = candidate
    if current:
        messages = messages_for_events(current_preamble, current)
        if total_message_chars(messages) > max_conversation_chars:
            oversized += 1
        windows.append(messages)
    return windows, oversized


def quality_weight(record: SourceRecord) -> float:
    weight = 1.0
    if record.old_reward == 0.0 or record.outcome_origin not in {"original_reward", "raw_reward"}:
        weight = min(weight, 0.85)
    if record.exception_type == "AgentTimeoutError":
        weight = min(weight, 0.70)
    elif record.exception_type == "CancelledError":
        weight = min(weight, 0.60)
    elif record.exception_type != "none":
        weight = min(weight, 0.50)
    return weight


def process_record(
    args: tuple[SourceRecord, int, int, int],
) -> dict[str, Any]:
    record, task_success_count, max_observation_chars, max_conversation_chars = args
    chain, chain_meta = load_chain(Path(record.trial_dir))
    aggregate_stats: Counter[str] = Counter()
    segments: list[Segment] = []
    for path, document in chain:
        segment, stats = document_to_segment(
            path,
            document,
            max_observation_chars=max_observation_chars,
        )
        aggregate_stats.update(stats)
        segments.append(segment)

    original_events = sum(len(segment.events) for segment in segments)
    duplicate_events_removed = sum(remove_exact_duplicate_events(segment) for segment in segments)
    active_indices = [index for index, segment in enumerate(segments) if segment.events]
    if not active_indices:
        if not segments:
            segments = [
                Segment(
                    source_path=str(Path(record.trial_dir) / "agent" / "trajectory.json"),
                    preamble=[
                        ContextMessage(
                            role="user",
                            content="Continue solving the current terminal task.",
                            step_loss_mask=0,
                        )
                    ],
                    events=[],
                )
            ]
        active_indices = [len(segments) - 1]
    final_index = active_indices[-1]
    tail_removed, tail_details = repair_final_tail(segments[final_index], record)
    synthetic_added, completion_reason = ensure_completion(segments[final_index])

    sft_rows: list[dict[str, Any]] = []
    turn_rows: list[dict[str, Any]] = []
    oversized_windows = 0
    repaired_events = 0
    trainable_events = 0
    for segment_index, segment in enumerate(segments):
        if not segment.events:
            continue
        repaired_events += len(segment.events)
        trainable_events += sum(event.trainable for event in segment.events)
        windows, oversized = split_segment_windows(segment, max_conversation_chars)
        oversized_windows += oversized
        for window_index, messages in enumerate(windows):
            row_id = f"{record.trajectory_id}__s{segment_index:03d}__w{window_index:03d}"
            sft_rows.append(
                {
                    "row_id": row_id,
                    "trajectory_id": record.trajectory_id,
                    "task": record.task,
                    "messages": messages,
                    "metadata": {
                        "trajectory_id": record.trajectory_id,
                        "task": record.task,
                        "source_rollout": record.source_rollout,
                        "source_run": record.source_run,
                        "trial_name": record.trial_name,
                        "native_segment_index": segment_index,
                        "window_index": window_index,
                        "exception_type_original": record.exception_type,
                        "outcome_origin": record.outcome_origin,
                        "quality_weight": quality_weight(record),
                        "task_success_count": task_success_count,
                        "task_choice_weight": 1.0 / task_success_count,
                        "original_trial_dir": record.trial_dir,
                        "original_segment_path": segment.source_path,
                    },
                }
            )
        for event_index, event in enumerate(segment.events):
            turn_rows.append(
                {
                    "trajectory_id": record.trajectory_id,
                    "task": record.task,
                    "source_rollout": record.source_rollout,
                    "segment_index": segment_index,
                    "event_index": event_index,
                    "source_path": event.source_path,
                    "source_step_id": event.source_step_id,
                    "trainable": event.trainable,
                    "valid_payload": event.valid_payload,
                    "synthetic": event.synthetic,
                    "task_complete": event.task_complete,
                    "mutating": event.mutating,
                    "successful_observation": event.successful_observation,
                }
            )

    window_count = len(sft_rows)
    trajectory_weight = quality_weight(record) / task_success_count
    for row in sft_rows:
        metadata = row["metadata"]
        metadata["trajectory_total_weight"] = trajectory_weight
        metadata["sample_weight"] = trajectory_weight / max(window_count, 1)
        row["meta"] = metadata

    manifest = dataclasses.asdict(record)
    manifest.update(
        {
            "chain": chain_meta,
            "task_success_count": task_success_count,
            "quality_weight": quality_weight(record),
            "task_choice_weight": 1.0 / task_success_count,
            "trajectory_total_weight": trajectory_weight,
            "original_live_agent_events": original_events,
            "exact_duplicate_events_removed": duplicate_events_removed,
            "post_solution_tail_events_removed": tail_removed,
            "repaired_agent_events": repaired_events,
            "trainable_agent_events": trainable_events,
            "synthetic_completion_added": synthetic_added,
            "completion_repair_reason": completion_reason,
            "tail_repair": tail_details,
            "sft_window_count": window_count,
            "oversized_window_count": oversized_windows,
            "repair_stats": dict(aggregate_stats),
        }
    )
    return {
        "manifest": manifest,
        "sft_rows": sft_rows,
        "turn_rows": turn_rows,
    }


def atomic_output_paths(output_dir: Path) -> dict[str, tuple[Path, Path]]:
    names = {
        "manifest": "repaired_pass_manifest.jsonl",
        "sft": "repaired_pass_sft.jsonl",
        "turns": "repaired_turn_index.jsonl",
    }
    return {
        key: (output_dir / f".{name}.tmp", output_dir / name)
        for key, name in names.items()
    }


def write_readme(output_dir: Path, summary: dict[str, Any]) -> None:
    text = f"""# Repaired Software Reconstruction Pass SFT

This directory was produced deterministically from the corrected Qwen3.8-Max
pass pool and the Qwen3.8-27B v6/v7 pass lists. Original rollout files were not
modified.

- Source trajectories: {summary['source_trajectories']}
- Unique tasks: {summary['unique_tasks']}
- SFT conversation windows: {summary['sft_rows']}
- Trainable agent turns: {summary['trainable_agent_events']}
- Synthetic completion turns: {summary['synthetic_completions']}
- Post-solution tail turns removed: {summary['post_solution_tail_events_removed']}

Files:

- `repaired_pass_manifest.jsonl`: one audit record per source trajectory.
- `repaired_pass_sft.jsonl`: SLIME-compatible messages with `step_loss_mask`.
- `repaired_turn_index.jsonl`: turn-level provenance without duplicated content.
- `summary.json`: aggregate counts and repair configuration.

Sampling should be task-aware. The metadata contains `task_choice_weight`,
`quality_weight`, `trajectory_total_weight`, and per-window `sample_weight`.
"""
    (output_dir / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=min(12, max(4, os.cpu_count() or 8)))
    parser.add_argument("--max-observation-chars", type=int, default=48_000)
    parser.add_argument("--max-conversation-chars", type=int, default=120_000)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    try:
        output_dir.relative_to(SOURCE_ROOT)
    except ValueError:
        pass
    else:
        raise SystemExit(
            f"refusing to write generated data under source tree: {SOURCE_ROOT}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = atomic_output_paths(output_dir)
    for temporary, final in paths.values():
        if final.exists() and not args.overwrite:
            raise SystemExit(f"output exists (pass --overwrite): {final}")
        temporary.unlink(missing_ok=True)

    log("loading 1422 source pass records")
    records = load_source_records()
    source_counts = Counter(record.source_rollout for record in records)
    if dict(source_counts) != EXPECTED_SOURCE_COUNTS:
        raise SystemExit(
            f"source count mismatch: expected={EXPECTED_SOURCE_COUNTS}, got={dict(source_counts)}"
        )
    if len({record.trajectory_id for record in records}) != len(records):
        raise SystemExit("duplicate trajectory_id detected")
    task_counts = Counter(record.task for record in records)
    log(f"sources={dict(source_counts)} total={len(records)} unique_tasks={len(task_counts)}")

    counters: Counter[str] = Counter()
    exception_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    start = time.time()
    work = [
        (
            record,
            task_counts[record.task],
            args.max_observation_chars,
            args.max_conversation_chars,
        )
        for record in records
    ]

    with (
        paths["manifest"][0].open("w", encoding="utf-8") as manifest_file,
        paths["sft"][0].open("w", encoding="utf-8") as sft_file,
        paths["turns"][0].open("w", encoding="utf-8") as turns_file,
        ProcessPoolExecutor(max_workers=args.workers) as pool,
    ):
        for index, processed in enumerate(pool.map(process_record, work, chunksize=1), start=1):
            manifest = processed["manifest"]
            manifest_file.write(json.dumps(manifest, ensure_ascii=False) + "\n")
            for row in processed["sft_rows"]:
                sft_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            for row in processed["turn_rows"]:
                turns_file.write(json.dumps(row, ensure_ascii=False) + "\n")

            counters["source_trajectories"] += 1
            counters["sft_rows"] += len(processed["sft_rows"])
            counters["turn_index_rows"] += len(processed["turn_rows"])
            counters["original_live_agent_events"] += manifest["original_live_agent_events"]
            counters["repaired_agent_events"] += manifest["repaired_agent_events"]
            counters["trainable_agent_events"] += manifest["trainable_agent_events"]
            counters["exact_duplicate_events_removed"] += manifest["exact_duplicate_events_removed"]
            counters["post_solution_tail_events_removed"] += manifest["post_solution_tail_events_removed"]
            counters["synthetic_completions"] += int(manifest["synthetic_completion_added"])
            counters["incomplete_chains"] += int(not manifest["chain"]["complete"])
            counters["oversized_windows"] += manifest["oversized_window_count"]
            counters["secret_redactions"] += int(
                (manifest.get("repair_stats") or {}).get("secret_redactions", 0)
            )
            counters["truncated_observations"] += int(
                (manifest.get("repair_stats") or {}).get("truncated_observations", 0)
            )
            exception_counts[manifest["exception_type"]] += 1
            outcome_counts[manifest["outcome_origin"]] += 1
            if not processed["sft_rows"]:
                counters["trajectories_without_sft_rows"] += 1

            if index % 50 == 0 or index == len(records):
                rate = index / max(time.time() - start, 1e-3)
                log(
                    f"processed {index}/{len(records)} ({rate:.1f} trajectories/s), "
                    f"sft_rows={counters['sft_rows']} trainable_turns={counters['trainable_agent_events']}"
                )

    if counters["source_trajectories"] != 1422:
        raise SystemExit(f"expected 1422 output trajectories, got {counters['source_trajectories']}")
    if counters["trajectories_without_sft_rows"]:
        raise SystemExit(
            f"{counters['trajectories_without_sft_rows']} trajectories produced no SFT rows"
        )

    for temporary, final in paths.values():
        temporary.replace(final)

    summary: dict[str, Any] = {
        "schema": "software-reconstruction-repaired-pass-sft-v1",
        "created_at_unix": int(time.time()),
        "source_trajectories": counters["source_trajectories"],
        "source_counts": dict(source_counts),
        "unique_tasks": len(task_counts),
        "task_multiplicity": dict(Counter(task_counts.values())),
        "exception_counts": dict(exception_counts),
        "outcome_origin_counts": dict(outcome_counts),
        **dict(counters),
        "configuration": {
            "workers": args.workers,
            "max_observation_chars": args.max_observation_chars,
            "max_conversation_chars": args.max_conversation_chars,
            "qmax_pool": str(QMAX_POOL),
            "v6_root": str(V6_ROOT),
            "v7_root": str(V7_ROOT),
        },
        "outputs": {key: str(final) for key, (_, final) in paths.items()},
        "elapsed_seconds": round(time.time() - start, 3),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_readme(output_dir, summary)
    log(f"done: {output_dir}")
    log(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
