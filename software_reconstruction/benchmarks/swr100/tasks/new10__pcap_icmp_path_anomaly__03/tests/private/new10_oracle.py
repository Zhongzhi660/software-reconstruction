
import hashlib, json, math, sqlite3

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

def stable_int(value, modulo=1000):
    text = json.dumps(value, sort_keys=True, default=str)
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(text)) % modulo

def stable_float(value, scale=1.0, offset=0.0):
    return offset + scale * (1 + stable_int(value, 997) / 997)

def sqlite_analytics(params):
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
    create table orders(id integer primary key, customer text, region text, amount real, day integer, status text);
    create table adjustments(order_id integer, delta real);
    """)
    rows = []
    depth = 6 + stable_int(params.get("join_depth"), 8)
    window = int(stable_float(params.get("date_window"), 25, 5))
    statuses = ["paid", "refunded", "pending"]
    for idx in range(36):
        rows.append((idx, f"C{idx%depth}", ["na","eu","apac"][idx%3], 10 + (idx * 7) % 53, idx % window, statuses[(idx + stable_int(params.get("null_policy"), 3)) % 3]))
    conn.executemany("insert into orders values (?,?,?,?,?,?)", rows)
    conn.executemany("insert into adjustments values (?,?)", [(idx, ((idx % 5) - 2) * 1.25) for idx in range(0, 36, 3)])
    q = """
    select region, status, round(sum(amount + coalesce(delta,0)), 3) as total, count(*) as n
    from orders left join adjustments on orders.id = adjustments.order_id
    where day <= ?
    group by region, status
    order by region, status
    """
    result = conn.execute(q, (window // 2,)).fetchall()
    conn.close()
    return {"window": window, "join_depth": depth, "rows": result}

def ajv_schema(params):
    import jsonschema
    min_items = 1 + stable_int({"required_fields": params.get("required_fields"), "params": params}, 5)
    item_count = min_items + stable_int({"union_branch": params.get("union_branch"), "params": params}, 4)
    require_meta = stable_int({"recursive_ref": params.get("recursive_ref"), "params": params}, 2) == 0
    allow_additional = stable_int({"additional_properties": params.get("additional_properties"), "params": params}, 2) == 0
    formats = ["baseline", "strict", "compat", "stress", "edge"]
    selected_format = str(params.get("format", formats[stable_int(params, len(formats))]))
    schema = {
        "type": "object",
        "required": ["kind", "items"] + (["meta"] if require_meta else []),
        "properties": {
            "kind": {"type": "string"},
            "items": {"type": "array", "minItems": min_items, "items": {"type": "number"}},
            "meta": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "additionalProperties": allow_additional,
    }
    payload = {"kind": selected_format, "items": list(range(item_count))}
    if require_meta:
        payload["meta"] = {"policy": str(params.get("additional_properties", "strict"))}
    if allow_additional:
        payload["extension"] = stable_int(params, 97)
    errors = sorted(e.path for e in jsonschema.Draft202012Validator(schema).iter_errors(payload))
    return {
        "min_items": min_items,
        "item_count": item_count,
        "require_meta": require_meta,
        "allow_additional": allow_additional,
        "selected_format": selected_format,
        "valid": not errors,
        "error_count": len(errors),
        "payload_key_count": len(payload),
    }

def z3_constraint_system(params):
    from z3 import If, Int, Optimize, Sum, sat
    n = 3 + stable_int(params.get("variable_count"), 5)
    lower = stable_int(params.get("bound_shape"), 4)
    penalty = 1 + stable_int(params.get("optimization_goal"), 7)
    xs = [Int(f"x{i}") for i in range(n)]
    opt = Optimize()
    for i, x in enumerate(xs):
        opt.add(x >= lower + i, x <= lower + i + 9)
    opt.add(Sum(xs) >= n * lower + stable_int(params.get("constraint_density"), 12))
    objective = Sum([If(x % 2 == 0, x * penalty, x) for x in xs])
    opt.minimize(objective)
    status = opt.check()
    if status != sat:
        return {"status": str(status), "n": n}
    model = opt.model()
    values = [model.eval(x).as_long() for x in xs]
    return {"status": "sat", "n": n, "lower": lower, "penalty": penalty, "values": values, "objective": sum((v * penalty if v % 2 == 0 else v) for v in values)}

def duckdb_reporting(params):
    import duckdb
    import pandas as pd
    n = 40 + stable_int(params.get("window_frame"), 40)
    df = pd.DataFrame({
        "grp": [f"G{i%5}" for i in range(n)],
        "region": [["na","eu","apac"][i%3] for i in range(n)],
        "amount": [(i * 13 + stable_int(params.get("type_cast_policy"), 17)) % 101 for i in range(n)],
    })
    con = duckdb.connect(database=":memory:")
    con.register("events", df)
    rows = con.execute("select region, grp, round(avg(amount), 3), count(*) from events group by region, grp order by region, grp").fetchall()
    return {"n": n, "rows": rows[:8], "row_count": len(rows)}

def opa_rego_policy(params):
    roles = ["viewer", "editor", "admin", "auditor"]
    resources = ["configmap", "secret", "deployment", "service"]
    identity = params.get("identity", params.get("role_matrix"))
    resource_shape = params.get("resource_shape", params.get("resource_tree"))
    namespace = str(params.get("namespace", params.get("environment_scope", "default")))
    role = roles[stable_int(identity, len(roles))]
    resource = resources[stable_int(resource_shape, len(resources))]
    exception = bool(params.get("exception", False))
    overlay_tier = stable_int(params.get("overlay"), 5)
    deny = resource == "secret" and role not in {"admin", "auditor"} and not exception
    allow = not deny and not (namespace.startswith("namespace_") and role == "viewer" and overlay_tier >= 3)
    obligations = sorted([f"audit:{namespace}", f"resource:{resource}", f"role:{role}", f"overlay:{overlay_tier}"])
    return {
        "role": role,
        "resource": resource,
        "namespace": namespace,
        "exception_applied": exception,
        "overlay_tier": overlay_tier,
        "allow": allow,
        "deny": deny,
        "obligations": obligations,
    }

def container_supply_chain(params):
    layers = []
    base = str(params.get("base_image", "python"))
    for idx in range(4 + stable_int(params.get("layer_order"), 4)):
        content = f"{base}:{idx}:{params.get('sbom_scope')}:{params.get('attestation_policy')}"
        layers.append(hashlib.sha256(content.encode()).hexdigest())
    merkle = digest(layers)
    vuln_budget = stable_int(params.get("vulnerability_policy"), 10)
    return {"base": base, "layer_count": len(layers), "merkle": merkle, "vuln_budget": vuln_budget, "attestation": digest({"layers": layers, "policy": params.get("attestation_policy")})[:16]}

def gdal_geospatial(params):
    from pyproj import Transformer
    from shapely.geometry import LineString, Polygon
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    shift = stable_float({"crs": params.get("crs"), "bbox": params.get("bbox"), "params": params}, 0.2)
    resolution = max(0.1, float(params.get("resolution", 1.0)))
    point_count = 12 + stable_int({"layer_filter": params.get("layer_filter"), "params": params}, 17)
    wave = 2 + stable_int(params.get("nodata"), 7)
    pts = [
        transformer.transform(
            -122 + i * (0.004 + resolution / 10000) + shift / 100,
            37 + math.sin(i / wave) / 100,
        )
        for i in range(point_count)
    ]
    line = LineString(pts)
    bbox = Polygon.from_bounds(min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))
    return {
        "length": round(float(line.length), 3),
        "area": round(float(bbox.area), 3),
        "bounds": [round(float(x), 3) for x in bbox.bounds],
        "point_count": point_count,
        "resolution": round(resolution, 3),
        "nodata_bucket": stable_int(params.get("nodata"), 11),
    }

def network_security_pcap(params):
    from scapy.all import IP, TCP, UDP, raw
    requested = max(8, int(float(params.get("port", params.get("session_window", 8)))))
    loss = bool(params.get("packet_loss", False))
    n = 8 + requested % 17
    if loss:
        n = max(4, n - 3)
    protocol = str(params.get("protocol", "mixed")).lower()
    destination_port = max(1, min(65535, requested))
    packets = []
    for idx in range(n):
        use_udp = protocol in {"udp", "dns", "dhcp"} or (protocol not in {"tcp", "http", "https"} and idx % 3 == 0)
        if use_udp:
            pkt = IP(src=f"10.0.0.{idx%5+1}", dst="10.0.1.2") / UDP(sport=2000+idx, dport=destination_port)
        else:
            pkt = IP(src=f"10.0.0.{idx%5+1}", dst="10.0.1.1") / TCP(sport=1000+idx, dport=destination_port)
        packets.append(pkt)
    digest_bytes = hashlib.sha256(b"".join(raw(p) for p in packets)).hexdigest()
    alert_threshold = stable_int(params.get("alert_rule"), 7)
    return {
        "packet_count": n,
        "protocol": protocol,
        "tcp": sum(1 for p in packets if TCP in p),
        "udp": sum(1 for p in packets if UDP in p),
        "destination_port": destination_port,
        "loss_applied": loss,
        "flow_score": stable_int(params.get("flow_pattern"), 997),
        "alert_score": stable_int(params.get("alert_rule"), 997),
        "alert_count": sum(1 for idx in range(n) if idx % 7 <= alert_threshold),
        "byte_count": sum(len(raw(p)) for p in packets),
        "digest": digest_bytes[:20],
    }

def document_ocr_publishing(params):
    from PIL import Image, ImageDraw, ImageFont
    page_range = max(1, int(float(params.get("page_range", params.get("layout_template", 1)))))
    dpi = max(1, int(float(params.get("dpi", params.get("dpi_profile", 72)))))
    width = 160 + stable_int({"page_range": page_range, "metadata": params.get("metadata"), "params": params}, 121)
    height = 80 + page_range % 97
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    language = str(params.get("language", params.get("language_model", "baseline")))
    font_name = str(params.get("font", params.get("table_structure", "default")))
    metadata_bucket = stable_int(params.get("metadata"), 17)
    text = f"{language} {font_name} page={page_range} meta={metadata_bucket}"
    line_count = 1 + dpi % 4
    for idx in range(line_count):
        draw.text((10, 8 + idx * 13), text[: max(8, len(text) - idx)], fill=0, font=ImageFont.load_default())
    hist = img.histogram()
    return {
        "size": list(img.size),
        "ink": int(sum(hist[:128])),
        "blank": int(sum(hist[128:])),
        "line_count": line_count,
        "text_length": len(text),
        "metadata_bucket": metadata_bucket,
        "text_digest": hashlib.sha256(text.encode()).hexdigest()[:16],
    }

import hashlib, json, os, subprocess, tempfile
from pathlib import Path


BASES = "ACGT"

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def seed_from(value):
    return sum((idx + 1) * ord(ch) for idx, ch in enumerate(str(value)))

def run(cmd, cwd, timeout=60):
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": p.returncode,
        "stdout": p.stdout[-4000:],
        "stderr": p.stderr[-4000:],
    }

def make_reference(params):
    seed = seed_from(params.get("reference", "")) + seed_from(params.get("region", ""))
    length = 900 + seed % 251
    seq = "".join(BASES[(seed + idx * 7 + idx // 11) % 4] for idx in range(length))
    return seq

def choose_region(params, length):
    seed = seed_from(params.get("region", ""))
    start = 30 + seed % max(1, length - 260)
    end = min(length, start + 120 + seed % 100)
    return start, end

def make_fastq_reads(seq, params):
    threshold = float(params.get("quality_threshold", 10))
    seed = seed_from(params)
    reads = []
    for idx in range(18):
        start = 1 + (seed + idx * 37) % (len(seq) - 80)
        length = 45 + (seed + idx * 11) % 31
        read = seq[start - 1:start - 1 + length]
        if idx % 4 == 0:
            read = read[:10] + "TTAA" + read[14:]
        q = max(2, min(40, int(threshold) + 10 + (idx % 9)))
        qual = chr(33 + q) * len(read)
        reads.append((f"read{idx:02d}", read, qual))
    return reads

def write_inputs(work, seq, params):
    (work / "ref.fa").write_text(">chr1\n" + "\n".join(seq[i:i+80] for i in range(0, len(seq), 80)) + "\n")
    reads = make_fastq_reads(seq, params)
    with (work / "reads.fastq").open("w") as fh:
        for name, read, qual in reads:
            fh.write(f"@{name}\n{read}\n+\n{qual}\n")

    seed = seed_from(params)
    mapq_base = max(1, min(60, int(float(params.get("quality_threshold", 10))) + 12))
    flag_seed = int(float(params.get("mapping_flags", 0)) * 1000)
    with (work / "sample.sam").open("w") as fh:
        fh.write("@HD\tVN:1.6\tSO:unsorted\n")
        fh.write(f"@SQ\tSN:chr1\tLN:{len(seq)}\n")
        fh.write("@RG\tID:rgA\tSM:sampleA\n@RG\tID:rgB\tSM:sampleB\n")
        for idx, (name, read, qual) in enumerate(reads):
            pos = 1 + (seed + idx * 29) % (len(seq) - len(read) - 1)
            flag = 16 if (flag_seed + idx) % 3 == 0 else 0
            rg = "rgA" if idx % 2 == 0 else "rgB"
            mapq = max(1, min(60, mapq_base + idx % 17))
            fh.write(f"{name}\t{flag}\tchr1\t{pos}\t{mapq}\t{len(read)}M\t*\t0\t0\t{read}\t{qual}\tRG:Z:{rg}\n")

    ploidy = max(1, min(6, int(params.get("ploidy", 2))))
    samples = [f"S{i}" for i in range(1, ploidy + 1)]
    with (work / "variants.vcf").open("w") as fh:
        fh.write("##fileformat=VCFv4.2\n")
        fh.write(f"##contig=<ID=chr1,length={len(seq)}>\n")
        fh.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        fh.write('##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read depth">\n')
        fh.write("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t" + "\t".join(samples) + "\n")
        for idx in range(8):
            pos = 40 + (seed + idx * 53) % (len(seq) - 80)
            ref = seq[pos - 1]
            alt = BASES[(BASES.index(ref) + (idx % 3) + 1) % 4]
            qual = round(float(params.get("quality_threshold", 10)) + 5 + idx * 3.3, 2)
            gts = []
            for sidx in range(len(samples)):
                gt = "0/1" if (idx + sidx) % 3 else "1/1"
                dp = 8 + ((seed + idx + sidx) % 31)
                gts.append(f"{gt}:{dp}")
            fh.write(f"chr1\t{pos}\tvar{idx}\t{ref}\t{alt}\t{qual}\tPASS\t.\tGT:DP\t" + "\t".join(gts) + "\n")

def smoke_scenario(params):
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        seq = make_reference(params)
        start, end = choose_region(params, len(seq))
        write_inputs(work, seq, params)

        commands = []
        for cmd in [
            ["samtools", "faidx", "ref.fa"],
            ["samtools", "view", "-bS", "sample.sam", "-o", "sample.bam"],
            ["samtools", "sort", "-o", "sample.sorted.bam", "sample.bam"],
            ["samtools", "index", "sample.sorted.bam"],
        ]:
            commands.append(run(cmd, work))

        min_mapq = max(1, min(50, int(float(params.get("quality_threshold", 10)))))
        flagstat = run(["samtools", "flagstat", "sample.sorted.bam"], work)
        depth = run(["samtools", "depth", "-a", "-r", f"chr1:{start}-{end}", "sample.sorted.bam"], work)
        filtered_count = run(["samtools", "view", "-c", "-q", str(min_mapq), "sample.sorted.bam"], work)
        norm = run(["bcftools", "norm", "-f", "ref.fa", "-o", "norm.vcf", "variants.vcf"], work)
        filt = run(["bcftools", "filter", "-i", f"QUAL>={min_mapq}", "-o", "filtered.vcf", "norm.vcf"], work)
        stats = run(["bcftools", "stats", "filtered.vcf"], work)
        seqkit_stats = run(["seqkit", "stats", "reads.fastq"], work)
        motif = "TTAA" if seed_from(params.get("reference", "")) % 2 == 0 else seq[start - 1:start + 2]
        seqkit_grep = run(["seqkit", "grep", "-s", "-p", motif, "reads.fastq"], work)
        commands.extend([flagstat, depth, filtered_count, norm, filt, stats, seqkit_stats, seqkit_grep])

        ok = all(item["returncode"] == 0 for item in commands)
        depth_lines = [line for line in depth["stdout"].splitlines() if line.strip()]
        return {
            "ok": ok,
            "reference_length": len(seq),
            "region": f"chr1:{start}-{end}",
            "min_mapq": min_mapq,
            "command_count": len(commands),
            "flagstat_digest": hashlib.sha256(flagstat["stdout"].encode()).hexdigest(),
            "depth_rows": len(depth_lines),
            "filtered_read_count": filtered_count["stdout"].strip(),
            "bcftools_stats_digest": hashlib.sha256(stats["stdout"].encode()).hexdigest(),
            "seqkit_stats_digest": hashlib.sha256(seqkit_stats["stdout"].encode()).hexdigest(),
            "seqkit_grep_digest": hashlib.sha256(seqkit_grep["stdout"].encode()).hexdigest(),
            "failed_commands": [item for item in commands if item["returncode"] != 0],
        }
ORACLES = {"samtools_bio_qc": smoke_scenario}

ORACLES.update({
    "sqlite_analytics": sqlite_analytics,
    "ajv_schema": ajv_schema,
    "z3_constraint_system": z3_constraint_system,
    "duckdb_reporting": duckdb_reporting,
    "opa_rego_policy": opa_rego_policy,
    "container_supply_chain": container_supply_chain,
    "gdal_geospatial": gdal_geospatial,
    "network_security_pcap": network_security_pcap,
    "document_ocr_publishing": document_ocr_publishing,
})
