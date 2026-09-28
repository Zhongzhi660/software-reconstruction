#!/usr/bin/env python3
"""Demo-specific, self-contained OpenSCAD adapters for true10 tasks."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

Params = dict[str, Any]
Adapter = Callable[[Params], str]


def num(p: Params, key: str, default: float, low: float, high: float) -> float:
    value = p.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return max(low, min(high, float(value)))


def count(p: Params, key: str, default: int, low: int, high: int) -> int:
    return max(low, min(high, round(num(p, key, default, low, high))))


def header(demo: str, p: Params) -> str:
    return (
        f"// demo_adapter: {demo}\n"
        f"// parameters: {json.dumps(p, sort_keys=True)}\n"
        "$fn=32;\n"
    )


def cable_clip_array(p: Params) -> str:
    n = count(p, "clip_count", 5, 2, 10)
    cable = num(p, "cable_diameter", 12, 4, 28)
    gap = num(p, "gap", 3, 0.8, 10)
    base = num(p, "base_thickness", 1.5, 0.6, 4)
    hole = num(p, "mount_holes", 3, 0.8, 10)
    lip = num(p, "snap_lip", 3, 0.8, 9)
    pitch = num(p, "array_pitch", 16, 8, 28)
    length = (n - 1) * pitch + cable + 14
    width = cable + 2 * gap + 8
    outer = cable / 2 + max(1.2, base)
    return header("openscad_bosl2_cable_clip_array", p) + f"""
module clip(x) {{
  translate([x,0,{base + outer:.5f}]) rotate([90,0,0]) difference() {{
    cylinder(h={width - 4:.5f},r={outer:.5f},center=true);
    cylinder(h={width + 2:.5f},r={cable / 2:.5f},center=true);
    translate([0,{outer:.5f},0]) cube([{gap:.5f},{2 * outer:.5f},{width + 3:.5f}],center=true);
  }}
  translate([x-{gap / 2:.5f},0,{base + 1.72 * outer:.5f}])
    cube([{lip:.5f},{width - 4:.5f},{max(base, 1):.5f}],center=true);
}}
render(convexity=10) difference() {{
  union() {{
    translate([0,0,{base / 2:.5f}]) cube([{length:.5f},{width:.5f},{base:.5f}],center=true);
    for(i=[0:{n - 1}]) clip((i-({n - 1})/2)*{pitch:.5f});
  }}
  for(x=[-{length / 2 - 5:.5f},{length / 2 - 5:.5f}])
    translate([x,0,-1]) cylinder(h={base + 2:.5f},d={hole:.5f});
}}
"""


def lattice_mount(p: Params) -> str:
    cells = count(p, "cell_count", 6, 3, 10)
    rib = num(p, "rib_width", 10, 3, 22) / 4
    holes = count(p, "hole_pattern", 4, 2, 9)
    pad = num(p, "load_pad", 4, 1, 12)
    fillet = num(p, "fillet", 2, 0.5, 11) / 4
    profile = num(p, "cross_section_profile", 3, 0.5, 7)
    clear = num(p, "assembly_clearance", 0.8, 0.2, 2)
    fast = count(p, "fastener_pattern", 4, 2, 8)
    order = num(p, "boolean_cut_order", 4, 3, 6)
    width = cells * 9 + 18 + clear
    depth = 34 + 2 * profile + holes * 0.15
    height = 4 + pad / 3
    return header("openscad_bosl2_lattice_mount_assembly", p) + f"""
render(convexity=10) difference() {{
 union() {{
  for(y=[-{depth / 2 - rib / 2:.5f},{depth / 2 - rib / 2:.5f}])
    translate([0,y,{height / 2:.5f}]) cube([{width:.5f},{rib:.5f},{height:.5f}],center=true);
  for(x=[-{width / 2 - rib / 2:.5f},{width / 2 - rib / 2:.5f}])
    translate([x,0,{height / 2:.5f}]) cube([{rib:.5f},{depth:.5f},{height:.5f}],center=true);
  for(i=[0:{cells}]) translate([-{width / 2 - rib:.5f}+i*{(width - 2 * rib) / cells:.5f},0,{height / 2:.5f}])
    rotate([0,0,(i%2)*{order:.5f}]) cube([{rib:.5f},{depth - 2 * rib:.5f},{height:.5f}],center=true);
  for(x=[-{width / 2 - 2 * rib:.5f},{width / 2 - 2 * rib:.5f}])
   for(y=[-{depth / 2 - 2 * rib:.5f},{depth / 2 - 2 * rib:.5f}])
    translate([x,y,{height:.5f}]) cylinder(h={pad / 2 + fillet:.5f},r={pad / 2 + fillet:.5f});
 }}
 for(i=[0:{holes - 1}]) translate([(i-({holes - 1})/2)*{(width - 10) / max(holes - 1, 1):.5f},0,-1])
  cylinder(h={height + pad + 3:.5f},d={1.5 + clear:.5f});
 for(i=[0:{fast - 1}]) rotate([0,0,i*{360 / fast:.5f}])
  translate([{min(width, depth) * 0.32:.5f},0,-1]) cylinder(h={height + 3:.5f},d={2 + profile / 4:.5f});
}}
"""


def living_hinge(p: Params) -> str:
    n = count(p, "knuckle_count", 6, 3, 9)
    pin = num(p, "pin_diameter", 14, 6, 28)
    leaf = num(p, "leaf_length", 18, 6, 36)
    clear = num(p, "clearance", 0.8, 0.2, 2.5)
    screws = count(p, "screw_pattern", 4, 2, 9)
    profile = num(p, "cross_section_profile", 3, 0.5, 7)
    assembly = num(p, "assembly_clearance", 0.8, 0.2, 2)
    fast = count(p, "fastener_pattern", 4, 2, 8)
    order = num(p, "boolean_cut_order", 4, 3, 6)
    width, thick, seg = 30 + 2 * profile, 2 + clear, (30 + 2 * profile) / n
    return header("openscad_bosl2_parametric_living_hinge", p) + f"""
render(convexity=10) difference() {{
 union() {{
  for(side=[-1,1]) translate([side*({leaf / 2 + pin / 2 + assembly:.5f}),0,{thick / 2:.5f}])
   cube([{leaf:.5f},{width:.5f},{thick:.5f}],center=true);
  for(i=[0:{n - 1}]) if((i%2)==0)
   translate([0,-{width / 2:.5f}+(i+.5)*{seg:.5f},{pin / 2 + thick / 2:.5f}])
    rotate([90,0,0]) cylinder(h={max(seg - assembly, .5):.5f},d={pin + profile / 2:.5f},center=true);
 }}
 translate([0,0,{pin / 2 + thick / 2:.5f}]) rotate([90,0,0])
  cylinder(h={width + 2:.5f},d={max(pin - 2 * clear, 1):.5f},center=true);
 for(side=[-1,1]) for(i=[0:{screws - 1}])
  translate([side*({pin / 2 + assembly + leaf * .55:.5f}),(i-({screws - 1})/2)*{width / max(screws, 1):.5f},-1])
   cylinder(h={thick + 3:.5f},d={1.5 + fast / 5:.5f});
 translate([0,0,-1]) rotate([0,0,{order:.5f}]) cube([{assembly:.5f},{width / 2:.5f},{thick + 3:.5f}],center=true);
}}
"""


def snap_fit_box(p: Params) -> str:
    size = num(p, "box_size", 18, 10, 30)
    snaps = count(p, "snap_count", 6, 3, 12)
    lip = num(p, "lip_depth", 7, 3, 12)
    wall = num(p, "wall", 1.5, 0.6, 3)
    corner = min(
        num(p, "corner_radius", 12, 4, 36) / 4,
        (18 + size * 0.72) / 3,
    )
    clear = num(p, "lid_clearance", 0.7, 0.2, 2.5)
    ribs = count(p, "rib_pattern", 4, 2, 8)
    x = 24 + size + corner * 0.17
    y = 18 + size * .72
    h = 10 + lip
    return header("openscad_bosl2_snap_fit_box", p) + f"""
module rp(x,y,z,r) {{ linear_extrude(height=z) offset(r=r) square([max(x-2*r,1),max(y-2*r,1)],center=true); }}
render(convexity=10) union() {{
 difference() {{
  rp({x:.5f},{y:.5f},{h:.5f},{corner:.5f});
  translate([0,0,{wall:.5f}]) rp({x - 2 * wall:.5f},{y - 2 * wall:.5f},{h + 1:.5f},{max(corner - wall, .2):.5f});
 }}
 translate([{x + 8:.5f},0,0]) difference() {{
  rp({x + 2 * clear:.5f},{y + 2 * clear:.5f},{wall + lip / 3:.5f},{corner:.5f});
  translate([0,0,{wall:.5f}]) rp({x - 2 * wall:.5f},{y - 2 * wall:.5f},{lip:.5f},{max(corner - wall, .2):.5f});
 }}
 for(i=[0:{snaps - 1}]) translate([(i-({snaps - 1})/2)*{(x - 8) / max(snaps - 1, 1):.5f},-{y / 2 + wall / 2:.5f},{h - lip / 3:.5f}])
  cube([{max(1, wall * 1.5):.5f},{wall:.5f},{lip / 2:.5f}],center=true);
 for(i=[1:{ribs}]) translate([-{x / 2:.5f}+i*{x / (ribs + 1):.5f},0,{wall / 2:.5f}])
  cube([{wall / 2:.5f},{y - 2 * wall:.5f},{wall:.5f}],center=true);
}}
"""


def fan_duct(p: Params) -> str:
    inlet = num(p, "inlet_size", 15, 8, 24)
    outlet = num(p, "outlet_size", 14, 7, 26)
    angle = num(p, "bend_angle", 90, 5, 359)
    ribs = count(p, "rib_count", 8, 4, 14)
    wall = num(p, "wall", 1.5, 0.6, 3)
    profile = num(p, "cross_section_profile", 3, 0.5, 7)
    clear = num(p, "assembly_clearance", 0.8, 0.2, 2)
    fast = count(p, "fastener_pattern", 4, 2, 8)
    order = num(p, "boolean_cut_order", 4, 3, 6)
    length = 28 + angle / 12
    rise = 8 + 10 * abs(math.sin(math.radians(angle)))
    return header("openscad_bosl2_swept_fan_duct_mount", p) + f"""
module path(d1,d2) {{
 hull() {{
  translate([-{length / 2:.5f},0,{inlet / 2 + wall:.5f}]) rotate([90,0,0]) cylinder(h=2,d=d1,center=true);
  translate([{length / 2:.5f},0,{rise + outlet / 2:.5f}]) rotate([90,0,{angle % 180:.5f}]) cylinder(h=2,d=d2,center=true);
 }}
}}
render(convexity=10) difference() {{
 union() {{
  path({inlet + 2 * wall + profile / 3:.5f},{outlet + 2 * wall + profile / 3:.5f});
  translate([0,0,{wall / 2:.5f}]) cube([{length + inlet + outlet:.5f},{max(inlet, outlet) + 12:.5f},{wall:.5f}],center=true);
  for(i=[1:{ribs}]) translate([-{length / 2:.5f}+i*{length / (ribs + 1):.5f},0,{rise / 2:.5f}])
   rotate([90,0,0]) cylinder(h={max(inlet, outlet) + 5:.5f},d={wall + .8:.5f},center=true);
 }}
 path({max(inlet - 2 * clear, 2):.5f},{max(outlet - 2 * clear, 2):.5f});
 for(i=[0:{fast - 1}]) rotate([0,0,i*{360 / fast:.5f}+{order:.5f}])
  translate([{length / 2 + max(inlet, outlet) / 2:.5f},0,-1]) cylinder(h={wall + 3:.5f},d=2.4);
}}
"""


def threaded_insert_mount(p: Params) -> str:
    pitch = num(p, "thread_pitch", 16, 8, 28)
    insert = num(p, "insert_diameter", 14, 7, 28)
    bosses = count(p, "boss_count", 6, 3, 10)
    wall = num(p, "wall", 1.5, 0.6, 3)
    clear = num(p, "clearance", 0.8, 0.2, 2.5)
    counter = num(p, "counterbore", 7, 4, 12)
    spacing = num(p, "mount_spacing", 20, 8, 34)
    plate_x = max(spacing + 18, (bosses - 1) * (insert / 2 + 4) + insert)
    plate_y, height = insert + 14, 7 + pitch / 5
    return header("openscad_bosl2_threaded_insert_mount", p) + f"""
render(convexity=10) difference() {{
 union() {{
  translate([0,0,{wall:.5f}]) cube([{plate_x:.5f},{plate_y:.5f},{2 * wall:.5f}],center=true);
  for(i=[0:{bosses - 1}]) translate([(i-({bosses - 1})/2)*{(plate_x - insert) / max(bosses - 1, 1):.5f},0,{2 * wall:.5f}])
   cylinder(h={height:.5f},d={insert + 2 * wall:.5f});
 }}
 for(i=[0:{bosses - 1}]) translate([(i-({bosses - 1})/2)*{(plate_x - insert) / max(bosses - 1, 1):.5f},0,{wall:.5f}]) union() {{
  cylinder(h={height + 3:.5f},d={insert + clear:.5f});
  translate([0,0,{height - counter / 4:.5f}]) cylinder(h={counter:.5f},d={insert + counter / 3:.5f});
 }}
 for(x=[-{spacing / 2:.5f},{spacing / 2:.5f}])
  translate([x,0,-1]) cylinder(h={2 * wall + 3:.5f},d={2 + clear + pitch / 20:.5f});
}}
"""


def bearing_block(p: Params) -> str:
    bearing = num(p, "bearing_od", 5, 1, 8)
    shaft = num(p, "shaft_d", 4, 1, 8)
    bolts = num(p, "bolt_spacing", 18, 7, 28)
    height = num(p, "block_height", 16, 5, 35)
    slot = num(p, "slot_length", 16, 6, 35)
    gap = num(p, "clamp_gap", 3, 0.6, 8)
    relief = num(p, "relief_cut", 2, 0.8, 5)
    length, width = max(bolts + 14, slot + 8), max(bearing + 14, 18)
    return header("openscad_mcad_bearing_block", p) + f"""
render(convexity=10) difference() {{
 union() {{
  translate([0,0,{height / 2:.5f}]) cube([{length:.5f},{width:.5f},{height:.5f}],center=true);
  for(x=[-{bolts / 2:.5f},{bolts / 2:.5f}]) translate([x,0,2])
   cylinder(h={height * .35:.5f},d={bearing + relief:.5f});
 }}
 translate([0,-{width / 2 + 1:.5f},{height * .58:.5f}]) rotate([-90,0,0])
  cylinder(h={width + 2:.5f},d={bearing + 4:.5f});
 translate([{length * .24:.5f},-{width / 2 + 1:.5f},{height * .3:.5f}]) rotate([-90,0,0])
  cylinder(h={width + 2:.5f},d={shaft:.5f});
 translate([0,0,{height - gap / 2:.5f}]) cube([{slot:.5f},{gap:.5f},{height:.5f}],center=true);
 for(x=[-{bolts / 2:.5f},{bolts / 2:.5f}]) translate([x,0,-1])
  cylinder(h={height + 2:.5f},d={2 + relief:.5f});
 translate([-{length / 2:.5f},0,{height * .25:.5f}])
  cube([{2 * relief:.5f},{width + 2:.5f},{2 * relief:.5f}],center=true);
}}
"""


def pulley(p: Params) -> str:
    teeth = count(p, "tooth_count", 8, 4, 16)
    pitch = num(p, "belt_pitch", 14, 8, 27)
    flange = num(p, "flange", 4, 2, 10)
    bore = num(p, "bore", 3, 0.7, 11)
    hub = num(p, "hub_height", 14, 7, 36)
    screw = num(p, "set_screw", 3, 0.8, 10)
    seat = num(p, "bearing_seat", 4, 1, 8)
    radius = max(9, min(45, teeth * pitch / (2 * math.pi)))
    depth = 1.2 + pitch / 15
    return header("openscad_mcad_parametric_pulley", p) + f"""
module wheel() {{ union() {{
 cylinder(h={hub:.5f},r={radius:.5f});
 for(i=[0:{teeth - 1}]) rotate([0,0,i*{360 / teeth:.5f}])
  translate([{radius + depth / 2:.5f},0,{hub / 2:.5f}]) cube([{depth:.5f},{max(2, pitch / 4):.5f},{hub * .72:.5f}],center=true);
 cylinder(h={flange / 2:.5f},r={radius + flange / 2:.5f});
 translate([0,0,{hub - flange / 2:.5f}]) cylinder(h={flange / 2:.5f},r={radius + flange / 2:.5f});
}} }}
render(convexity=10) difference() {{
 wheel();
 translate([0,0,-1]) cylinder(h={hub + 2:.5f},d={bore:.5f});
 translate([0,0,{hub - seat:.5f}]) cylinder(h={seat + 1:.5f},d={bore + 2 * seat:.5f});
 translate([{radius / 2:.5f},0,{hub / 2:.5f}]) rotate([0,90,0])
  cylinder(h={radius + flange:.5f},d={screw:.5f});
}}
"""


def planetary(p: Params) -> str:
    mod = num(p, "gear_mod", 4, 1.5, 8) / 3
    planets = count(p, "planet_count", 5, 3, 10)
    teeth = count(p, "tooth_count", 9, 4, 16)
    helix = num(p, "helix", 2.5, 1, 10)
    phase = num(p, "phase", 180, 90, 310)
    thick = num(p, "thickness", 1.2, 0.4, 2.5) * 4
    sun, pr = teeth * mod / 2, max(3, teeth * mod * .26)
    orbit, outer = sun + pr + 1.5 * mod, sun + 2 * pr + 3.5 * mod
    pt = max(4, teeth // 2)
    return header("openscad_planetary_gears", p) + f"""
module gear2d(n,r,d) {{ union() {{
 circle(r=r);
 for(i=[0:n-1]) rotate(i*360/n) translate([r,0]) square([d,max(1,d*1.4)],center=true);
}} }}
module gear3d(n,r,d,h,tw=0) {{ linear_extrude(height=h,twist=tw,slices=8,convexity=10) gear2d(n,r,d); }}
render(convexity=10) union() {{
 gear3d({teeth},{sun:.5f},{mod:.5f},{thick:.5f},{2 * helix:.5f});
 for(i=[0:{planets - 1}]) rotate([0,0,i*{360 / planets:.5f}+{phase:.5f}])
  translate([{orbit:.5f},0,0]) gear3d({pt},{pr:.5f},{.8 * mod:.5f},{thick:.5f},-{2 * helix:.5f});
 difference() {{
  cylinder(h={thick:.5f},r={outer:.5f});
  translate([0,0,-1]) cylinder(h={thick + 2:.5f},r={orbit + pr + .4 * mod:.5f});
 }}
}}
"""


def enclosure(p: Params) -> str:
    xy = num(p, "xy_scale", 18, 10, 28)
    height = num(p, "height", 17, 10, 28)
    wall = num(p, "wall", 1.5, 0.6, 3)
    port = num(p, "port", 4, 1, 10)
    bosses = count(p, "bosses", 4, 2, 10)
    ribs = count(p, "ribs", 4, 2, 10)
    x, y = 18 + 1.7 * xy, 14 + 1.25 * xy
    radius = min(5 + xy / 10, min(x, y) / 4)
    return header("openscad_skinned_enclosure", p) + f"""
module rp(x,y,z,r) {{ linear_extrude(height=z) offset(r=r) square([max(x-2*r,1),max(y-2*r,1)],center=true); }}
render(convexity=10) difference() {{
 union() {{
  difference() {{
   rp({x:.5f},{y:.5f},{height:.5f},{radius:.5f});
   translate([0,0,{wall:.5f}]) rp({x - 2 * wall:.5f},{y - 2 * wall:.5f},{height + 1:.5f},{max(radius - wall, .2):.5f});
  }}
  for(i=[0:{bosses - 1}]) rotate([0,0,i*{360 / bosses:.5f}])
   translate([{min(x, y) * .31:.5f},0,{wall:.5f}]) difference() {{
    cylinder(h={height * .45:.5f},d={port + 2 * wall:.5f});
    translate([0,0,-1]) cylinder(h={height:.5f},d={max(port / 2, 1):.5f});
   }}
  for(i=[0:{ribs - 1}]) rotate([0,0,i*{360 / ribs:.5f}])
   translate([{x / 2 + wall / 2:.5f},0,{height / 3:.5f}])
    cube([{wall:.5f},{2 + xy / 12:.5f},{height * .55:.5f}],center=true);
 }}
 translate([{x / 2:.5f},0,{height * .55:.5f}]) rotate([0,90,0])
  cylinder(h={4 * wall:.5f},d={port + wall:.5f},center=true);
}}
"""


ADAPTERS: dict[str, Adapter] = {
    "openscad_bosl2_cable_clip_array": cable_clip_array,
    "openscad_bosl2_lattice_mount_assembly": lattice_mount,
    "openscad_bosl2_parametric_living_hinge": living_hinge,
    "openscad_bosl2_snap_fit_box": snap_fit_box,
    "openscad_bosl2_swept_fan_duct_mount": fan_duct,
    "openscad_bosl2_threaded_insert_mount": threaded_insert_mount,
    "openscad_mcad_bearing_block": bearing_block,
    "openscad_mcad_parametric_pulley": pulley,
    "openscad_planetary_gears": planetary,
    "openscad_skinned_enclosure": enclosure,
}


def render_demo_scad(demo_id: str, parameters: Params) -> str:
    try:
        adapter = ADAPTERS[demo_id]
    except KeyError as exc:
        raise KeyError(f"no OpenSCAD adapter for {demo_id}") from exc
    return adapter(parameters)
