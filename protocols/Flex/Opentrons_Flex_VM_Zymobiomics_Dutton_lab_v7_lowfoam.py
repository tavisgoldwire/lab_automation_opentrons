"""
ZymoBIOMICS 96 DNA Kit on the Opentrons Flex + Vacuum Module (Dutton lab v7, low-foam).

Low-foam changes from v7 (2026-11-22 AcroPrep foam test: 400 uL Binding Buffer drained in
~75 s at 20% pump power with no foam over a 5 min pull; 10% moved nothing):
  - Load pulls and Wash 1 run at Pull Power (default 20%) instead of 100%. Wash 1 ends with
    30 s at Wash 1 Finish Power (35%) to clear slow wells. Wash 2 runs at Wash 2 Power (55%).
    Dry Power (default 100%) is a setting. Pull times cut from ~62 min to ~27 min total.
  - First Binding Buffer add dispenses above the expected liquid level, so the tip never touches
    the sample before returning to the trough. The second add dispenses low (tip goes on to mix).
  - No air gap or blow-out into liquid on the Binding Buffer add or the spin-plate loads.
    The load tip keeps a 20 uL reserve, so it never pushes air through the liquid.
  - Wash Soak (default 60 s): every wash sits on the membrane, vacuum off, before its pull.
  - Elution setting (default Centrifuge): robot does the vacuum dry and adds the elution water
    twice (same tips), pausing for the operator's dry spin and two centrifuge elutions.
    Old note: for an off-deck dry spin and
    centrifuge elution. Vacuum elution sprayed foam across the plate on 2026-11-23.
  - Gentler Binding Buffer mix: 5 x 600 uL at 80 uL/s (was 10 x 900 uL at 150 uL/s).

Before the run (manual): prefilter the lysate through the AcroPrep prefilter plate and put
the clarified lysate in a 2 mL deep-well plate in A2.

Deck
  A1 B1 D1  1000 uL tip racks on 96 adapters      C4  50 uL tip rack (elution)
  A2        clarified lysate (deep-well plate)    A3  vacuum module + tall collar + AcroPrep spin plate
  B2 B3     Binding Buffer, Wash Buffer 1         D2  7.25 mm spacer + NEST PCR plate (elution)
  C2        Wash Buffer 2                         C1  temperature module + flat adapter + water
  D3        waste chute
  Reagents are in 12-well reservoirs: with full pickup at A1, tip column k draws from well k.

Partial plates (Sample Columns < 12): tip racks hold tips in columns 1-N only, samples go in
columns 1-N, and only reservoir wells 1-N are filled. Seal spin-plate columns N+1 to 12.

Ends at elution. HRC inhibitor removal (kit step 14) is done off-deck.
"""

from opentrons import protocol_api

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Flex + Vacuum Module (Dutton lab v7)",
    "author": "Tavis Goldwire",
    "description": "Spin-plate DNA extraction on the vacuum manifold, 8-96 samples, through elution.",
}
requirements = {"robotType": "Flex", "apiLevel": "2.31"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 1}
SPIN_PLATE = "cytiva_96_wellplate_1000ul_shorttip_filter"
SPACER = "custom_vacuum_manifold_spacer_7_25mm"
ELUTION_PLATE = "opentrons_96_wellplate_200ul_pcr_full_skirt"
SAMPLE_PLATE = "nest_96_wellplate_2ml_deep"
RESERVOIR = "nest_12_reservoir_22ml"
RESERVOIR_MAX = 15_000      # uL per reservoir well
WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw

# Volumes, uL per well
BINDING_VOL = 600           # added twice
LOADS = 4                   # lysate + binding buffer goes onto the spin plate in this many loads
WASH1_VOL = 400
WASH2_VOLS = (700, 200)        # kit Wash 2: 700 then 200
EXTRA_WASH_VOL = 700           # Extra Wash setting: 80% ethanol (C3) or a third Wash 2
MIX_VOL = 600
MIX_REPS = 5
AIR_GAP = 20                # washes only; never dispensed into liquid
RESERVE_VOL = 20            # kept in the load tip so no air is pushed through the load; discarded with the tip

# Flow rates, uL/s: (aspirate, dispense)
RATES = {
    "binding": (80, 80),
    "mix": (80, 80),
    "lysate": (100, 25),
    "wash": (150, 180),
    "water": (6, 10),
}

# Heights, mm. Spin plate heights are above the membrane (the definition's well bottom).
ASP_Z = 0.75                # above well bottom, every aspiration
MIX_DISP_Z = 5              # above the sample well bottom
TOP_Z = -5                  # below well top: washes and blow-outs
PARK_Z = 5                  # above the sample plate, where tips wait during a pull
EXIT_SPEED = 5              # mm/s, leaving the sample well after each load draw
LOAD_Z = 5                  # above the membrane, lysate dispense. NOT tested on this plate
ELUTION_Z = 4               # above the membrane, water dispense. NOT tested on this plate

# Vacuum (pump power, no pressure setpoint). Powers are runtime parameters; times are below.

# Pull times, set from the 2026-11-22 test (400 uL drained in ~75 s at 20%). Running long at
# Pull Power doesn't foam, so these keep margin over the measured drain time.
LOAD_TIME = 120             # s, after loads 1-3 (was 300)
FINAL_LOAD_TIME = 180       # s, after the last load (was 600)
WASH1_TIME = 150            # s at Pull Power, then the finish below (was 540)
FINISH_TIME = 60            # s, stronger finish that clears slow wells (3 wells kept Wash 1 on 2026-11-22)
WASH2_TIMES = (180, 120)       # s at Wash 2 Power, matching WASH2_VOLS (was 540 each)
EXTRA_WASH_TIME = 180          # s at Wash 2 Power
DRY_TIME = 600              # s, extra pull to dry the membrane (ethanol removal)
CLEAR_Z = 6                 # mm above the flat-well estimate of the liquid level; the pyramid bottom
                            # raises the real level ~2 mm, so this leaves ~4 mm of clearance
ELUTION_POWERS = (50, 75, 100)  # %, stepped up over ELUTION_TIME
ELUTION_TIME = 240          # s, total
ELUTION_SOAK = 300          # s, water on the membrane before the elution pull
DRY_RUN_PULL = 5            # s, every pull in a dry run

# Gripper
SPACER_GRIP_RAISE = 5       # mm above default grip, clears the manifold rim
MODULE_DROP_X = 0.0        # drops on the vacuum module land ~1 mm right 
# keeps clipping left side. 


def add_parameters(p: protocol_api.ParameterContext):
    p.add_bool(
        variable_name="dry_run",
        display_name="Dry Run",
        description="5 s vacuums, no delays, tips returned to the rack.",
        default=False,
    )
    p.add_str(
        variable_name="end_mode",
        display_name="Elution",
        description="Vacuum: elute on deck. Centrifuge: pauses for dry spin and two spun elutions.",
        default="centrifuge",
        choices=[
            {"display_name": "Centrifuge (manual spins)", "value": "centrifuge"},
            {"display_name": "Vacuum (on deck)", "value": "vacuum"},
        ],
    )
    p.add_str(
        variable_name="extra_wash",
        display_name="Extra Wash",
        description="Extra 700 uL wash after the kit washes, to clear salt left in the membrane.",
        default="ethanol",
        choices=[
            {"display_name": "80% ethanol, last (C3)", "value": "ethanol"},
            {"display_name": "Third Wash 2", "value": "wash2"},
            {"display_name": "None", "value": "none"},
        ],
    )
    p.add_int(
        variable_name="wash_soak",
        display_name="Wash Soak",
        description="Vacuum off: each wash sits on the membrane this long before its pull.",
        default=60,
        minimum=0,
        maximum=300,
        unit="s",
    )
    p.add_int(
        variable_name="sample_columns",
        display_name="Sample Columns",
        description="Tips, samples and reagent wells in columns 1 to this number. 6 = 48 samples.",
        default=6,
        minimum=1,
        maximum=12,
    )
    p.add_int(
        variable_name="lysate_volume",
        display_name="Lysate Volume",
        description="Clarified lysate per sample well. Kit: up to 400 uL.",
        default=400,
        minimum=100,
        maximum=400,
        unit="uL",
    )
    p.add_float(
        variable_name="elution_volume",
        display_name="Elution Volume",
        description="Water per well, delivered with 50 uL tips.",
        default=50.0,
        minimum=20.0,
        maximum=50.0,
        unit="uL",
    )
    p.add_int(
        variable_name="pull_power",
        display_name="Pull Power",
        description="Pump % for loads and washes. 20% drained 400 uL in ~75 s, no foam. 10% failed.",
        default=20,
        minimum=15,
        maximum=100,
        unit="%",
    )
    p.add_int(
        variable_name="wash1_finish_power",
        display_name="Wash 1 Finish Power",
        description="Pump % for the last 60 s of the Wash 1 pull. 35% tested foam-free; 50% untested.",
        default=50,
        minimum=15,
        maximum=100,
        unit="%",
    )
    p.add_int(
        variable_name="wash2_power",
        display_name="Wash 2 Power",
        description="Pump % for the Wash 2 and extra-wash pulls (ethanol washes, low foam risk).",
        default=70,
        minimum=15,
        maximum=100,
        unit="%",
    )
    p.add_int(
        variable_name="dry_power",
        display_name="Dry Power",
        description="Pump % for the 10 min membrane dry (runs in both modes). Evaporates ethanol.",
        default=100,
        minimum=15,
        maximum=100,
        unit="%",
    )
    p.add_int(
        variable_name="elution_temp",
        display_name="Elution Water Temp",
        description="C1 module heats the water from the start of Wash 2. 0 = no heating.",
        default=65,
        minimum=0,
        maximum=70,
        unit="C",
    )


def run(ctx: protocol_api.ProtocolContext):
    p = ctx.params
    dry = p.dry_run
    n = p.sample_columns

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware(SPIN_PLATE, "AcroPrep spin plate", **CUSTOM)
    spacer = ctx.load_adapter(SPACER, "D2", **CUSTOM)
    elution_plate = spacer.load_labware(ELUTION_PLATE, "Elution plate")
    samples = ctx.load_labware(SAMPLE_PLATE, "A2", "Clarified lysate")
    temp_mod = ctx.load_module("temperatureModuleV2", "C1")
    water_adapter = temp_mod.load_adapter("opentrons_universal_flat_adapter")

    tip_adapters = {s: ctx.load_adapter("opentrons_flex_96_tiprack_adapter", s) for s in ("A1", "B1", "D1")}
    racks = [a.load_labware("opentrons_flex_96_tiprack_1000ul") for a in tip_adapters.values()]
    elution_tips = ctx.load_labware("opentrons_flex_96_tiprack_50ul", "C4", "50 uL tips")
    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=racks)

    # ---------------- Liquids ----------------
    def trough(slot, name, color, per_tip_ul, on=None):
        """Fill wells 1-n of a 12-well reservoir with what each tip column draws, plus margin."""
        reservoir = on.load_labware(RESERVOIR, name) if on else ctx.load_labware(RESERVOIR, slot, name)
        fill = 8 * per_tip_ul + WELL_MARGIN
        if fill > RESERVOIR_MAX:
            raise ValueError(f"{name} needs {fill} uL per well; the reservoir holds {RESERVOIR_MAX}.")
        liquid = ctx.define_liquid(name, "ZymoBIOMICS", color)
        for well in reservoir.wells()[:n]:
            well.load_liquid(liquid, fill)
        return reservoir["A1"]

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 2 * BINDING_VOL)
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", WASH1_VOL)
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E",
                   sum(WASH2_VOLS) + (EXTRA_WASH_VOL if p.extra_wash == "wash2" else 0))
    ethanol = (trough("C3", "80% ethanol", "#B3E5FC", EXTRA_WASH_VOL)
               if p.extra_wash == "ethanol" else None)
    n_elutions = 1 if p.end_mode == "vacuum" else 2
    water = trough("C1", "Nuclease-free water", "#0048FF", n_elutions * p.elution_volume, on=water_adapter)

    lysate = ctx.define_liquid("Clarified lysate", "Prefiltered by hand", "#B266FF")
    for column in samples.columns()[:n]:
        for well in column:
            well.load_liquid(lysate, p.lysate_volume)

    sample = samples["A1"]
    spin = spin_plate["A1"]
    # RESERVE_VOL of the mix stays in the tip and is discarded (~1% of the sample).
    load_vol = (p.lysate_volume + 2 * BINDING_VOL - RESERVE_VOL) / LOADS

    # ---------------- Helpers ----------------
    def hold(seconds):
        if not dry:
            ctx.delay(seconds=seconds)

    def pull(seconds, power=p.pull_power, vent=True):
        """Run the pump for `seconds`, then vent."""
        if dry:
            seconds = DRY_RUN_PULL
        vm.close_vent()
        task = vm.start_set_vacuum_power(power, seconds, vent_after=vent, equalize_timeout_s=20)
        ctx.wait_for_tasks([task])

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def wash(volume, source):
        pip.aspirate(volume, source.bottom(ASP_Z))
        pip.air_gap(AIR_GAP)
        pip.dispense(volume + AIR_GAP, spin.top(TOP_Z))
        pip.blow_out(spin.top(TOP_Z))

    # ---------------- 1. Binding buffer + mix ----------------
    # Binding Buffer goes in low and slow with no air gap, so no air is pushed through the sample.
    # push_out=0 until the final blow-out (above the liquid), so the tips stay wet between steps.
    pip.pick_up_tip()
    set_rates("binding")
    # First add: the tip returns to the trough afterwards, so it must never touch the sample.
    # It dispenses CLEAR_Z above where the liquid will stand once this add is in.
    # Second add: the tip goes on to mix, so it can dispense low, under the surface.
    area = sample.length * sample.width
    first_level = (p.lysate_volume + BINDING_VOL) / area
    first_z = min(first_level + CLEAR_Z, sample.depth + TOP_Z)
    for z in (first_z, MIX_DISP_Z):
        pip.aspirate(BINDING_VOL, binding.bottom(ASP_Z))
        pip.dispense(BINDING_VOL, sample.bottom(z), push_out=0)

    set_rates("mix")
    for _ in range(MIX_REPS):
        pip.aspirate(MIX_VOL, sample.bottom(ASP_Z))
        pip.dispense(MIX_VOL, sample.bottom(MIX_DISP_Z), push_out=0)
    pip.blow_out(sample.top(TOP_Z))

    # ---------------- 2. Load spin plate, pump on while dispensing ----------------
    # No air gap, no blow-out: the tip keeps RESERVE_VOL so it never pushes air through the load.
    set_rates("lysate")
    for i in range(LOADS):
        vm.close_vent()
        pump = vm.start_set_vacuum_power(p.pull_power)
        pip.aspirate(load_vol + (RESERVE_VOL if i == 0 else 0), sample.bottom(ASP_Z))
        pip.move_to(sample.top(), speed=EXIT_SPEED)
        pip.dispense(load_vol, spin.bottom(LOAD_Z), push_out=0)
        pip.move_to(sample.top(PARK_Z))
        vm.stop_vacuum_pump()
        ctx.wait_for_tasks([pump])
        pull(FINAL_LOAD_TIME if i == LOADS - 1 else LOAD_TIME)
    discard_tip()

    # ---------------- 3. Wash 1 ----------------
    # Water heating starts here (~20 min before elution) now that the wash pulls are shorter.
    on_deck_elution = p.end_mode == "vacuum"
    heat = p.elution_temp > 0 and not dry
    if heat:
        temp_mod.start_set_temperature(p.elution_temp)
    pip.pick_up_tip()
    set_rates("wash")
    wash(WASH1_VOL, wash1)
    discard_tip()
    hold(p.wash_soak)                            # contact time before the pull (Zymo: more time helps)
    pull(WASH1_TIME, vent=False)                 # Pull Power, then a short stronger finish
    pull(FINISH_TIME, p.wash1_finish_power)

    # ---------------- 4. Wash 2 (x2) + Extra Wash ----------------
    # 2026-11-23: two runs released 3-15x more lambda in a 2nd elution than the 1st, and the 1st
    # eluates carried a large 230 nm salt peak: salt held in the membrane. Zymo (B. Farthing):
    # salt carryover is common on manifolds; follow the standard washes with ethanol washes.
    # 80% ethanol goes LAST so the liquid left in the membrane is salt-free ethanol for the dry spin.
    # The Wash 2 tip also does the extra wash (it never touches liquid; only 3 tip racks).
    steps = list(zip(WASH2_VOLS, [wash2] * len(WASH2_VOLS), WASH2_TIMES))
    if p.extra_wash == "wash2":
        steps.insert(0, (EXTRA_WASH_VOL, wash2, EXTRA_WASH_TIME))
    elif p.extra_wash == "ethanol":
        steps.append((EXTRA_WASH_VOL, ethanol, EXTRA_WASH_TIME))
    pip.pick_up_tip()
    set_rates("wash")
    for i, (vol, source, secs) in enumerate(steps):
        wash(vol, source)
        if i == len(steps) - 1:
            discard_tip()
        else:
            pip.move_to(sample.top(PARK_Z))
        hold(p.wash_soak)
        pull(secs, p.wash2_power)

    # Vacuum dry runs in both modes: airflow evaporates the ethanol left in the membrane.
    pull(DRY_TIME, p.dry_power)

    # 2026-11-23: vacuum elution sprayed foam across the whole elution plate (unused columns
    # too) and left most lambda on the membrane. Centrifuge mode: the robot does the water, the
    # operator does the spins. The plate stays on the collar; the vacuum stays off (nothing drains
    # without it: 10% pump power moved nothing on 2026-11-22).
    if not on_deck_elution:
        ctx.move_labware(racks[-1], "D2" if dry else chute, use_gripper=True)
        ctx.move_labware(elution_tips, tip_adapters["D1"], use_gripper=True)
        ctx.pause(
            "DRY SPIN: take the binding plate off the collar, spin on a waste plate 1,000 x g "
            "5-10 min, wipe the underside, note any residual liquid. Put it back on the collar, "
            "press all four corners down, then Resume."
        )
        if heat:
            temp_mod.await_temperature(p.elution_temp)
        set_rates("water")
        pip.flow_rate.blow_out = 10
        for n in (1, 2):
            pip.pick_up_tip(elution_tips["A1"])       # same tips both times: they never touch the membrane
            pip.aspirate(p.elution_volume, water.bottom(ASP_Z))
            pip.dispense(p.elution_volume, spin.bottom(ELUTION_Z))
            pip.blow_out(spin.bottom(ELUTION_Z))
            if n == 1:
                pip.return_tip()
            else:
                discard_tip()
            hold(ELUTION_SOAK)
            ctx.pause(
                f"ELUTION {n}: water soaked {ELUTION_SOAK // 60} min. Move the binding plate onto "
                f"elution plate {n}, spin 1,000 x g 5 min. "
                + ("Then put the binding plate back on the collar, press down, and Resume."
                   if n == 1 else "Done. Qubit plates 1 and 2 separately.")
            )
        if heat:
            temp_mod.deactivate()
        return

    # ---------------- 5. Stack spin plate on elution plate, swap tips ----------------
    ctx.move_labware(collar, vm.manifold_dock, use_gripper=True)
    ctx.move_labware(
        spacer, vm, use_gripper=True,
        pick_up_offset={"x": 0, "y": 0, "z": SPACER_GRIP_RAISE},
        drop_offset={"x": MODULE_DROP_X, "y": 0, "z": SPACER_GRIP_RAISE},
    )
    ctx.move_labware(
        spin_plate, elution_plate, use_gripper=True,
        drop_offset={"x": MODULE_DROP_X, "y": 0, "z": 0},
    )
    ctx.move_labware(collar, vm, use_gripper=True)

    ctx.move_labware(racks[-1], "D2" if dry else chute, use_gripper=True)
    ctx.move_labware(elution_tips, tip_adapters["D1"], use_gripper=True)

    # ---------------- 6. Elution ----------------
    pip.pick_up_tip(elution_tips["A1"])
    set_rates("water")
    pip.flow_rate.blow_out = 10  # slow, so the blow-out doesn't spray the membrane
    if heat:
        temp_mod.await_temperature(p.elution_temp)
    pip.aspirate(p.elution_volume, water.bottom(ASP_Z))
    pip.dispense(p.elution_volume, spin.bottom(ELUTION_Z))
    pip.blow_out(spin.bottom(ELUTION_Z))
    discard_tip()
    if heat:
        temp_mod.deactivate()

    hold(ELUTION_SOAK)
    step = ELUTION_TIME // len(ELUTION_POWERS)
    for power in ELUTION_POWERS[:-1]:
        pull(step, power, vent=False)
    pull(ELUTION_TIME - step * (len(ELUTION_POWERS) - 1), ELUTION_POWERS[-1])
    ctx.comment("Done. Next, off-deck: HRC plate, 3,500 x g for 3 min (kit step 14).")
