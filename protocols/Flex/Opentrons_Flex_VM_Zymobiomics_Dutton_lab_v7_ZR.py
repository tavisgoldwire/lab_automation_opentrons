"""
ZymoBIOMICS 96 DNA Kit on the Opentrons Flex + Vacuum Module (Dutton lab V7).

Deck
  A1 B1 D1  1000 uL tip racks on 96 adapters     C4  50 uL tip rack (elution)
  A2        sample plate, Lysate Volume/well     B4  paper towel (blot, optional)
  B2 B3     Binding Buffer, Wash Buffer 1        A3  vacuum module + tall collar + spin plate
  C2        Wash Buffer 2                        D2  tall spacer + elution plate
  C1        temperature module + universal flat adapter + water reservoir
  D3        waste chute                          C3  empty
  Reagents are in 12-well reservoirs: tip column k always lands in reservoir well k.

Heated elution water: the C1 module starts heating at Wash 2 (about 30 min before elution) and
switches off once the water is drawn. Zymo's low-yield FAQ for this kit: "Apply heated elution
buffer (60-70 C) and allow elution buffer to incubate on the column for several minutes."
Before elution the protocol waits for the module to reach its setpoint. The water in the plastic
reservoir will lag below that: measure it once on a full dry run.
The universal flat adapter is defined by Opentrons for the Heater-Shaker. The API accepts it on
the temperature module but doesn't check the physical fit: run Labware Position Check on the
water reservoir, and watch the 50 uL tips at the water draw (0.75 mm off the floor) on a dry run.

Partial plates (Sample Columns < 12)
  Full 96-tip pickup throughout, but every tip rack holds tips only in columns 1-N. The empty
  nozzles move with the head and never reach liquid, so only reservoir wells 1-N need reagent.
  Samples go in plate columns 1-N. Seal spin-plate columns N+1 to 12 so the vacuum doesn't
  pull air through their dry membranes.

Vacuum: every pull except elution runs the pump at a fixed power (Pump Power), with no pressure
setpoint. Observed on the robot: under pressure control the pump stops once it reaches the
setpoint, so liquid only trickles through. Full power drained the plate much better (2026-10-13).
  Lysate: lysate + 1200 uL binding buffer, in 4 equal loads (400 uL each at the kit's 400 uL of
  supernatant, 350 uL at 200 uL). The pump starts before each aspirate, the lysate goes in low and
  slowly (vacuum-on loading, from ZR-96 v2), the tips park above the sample plate, then the pump
  runs for Load Pull Time (Final Load Pull Time after the 4th load). At 400 uL a load can't pool
  above the Wash 1 (400 uL) line, so every wash reaches the top of the binding-buffer line.
  Elution: power in three equal steps over Elution Vacuum Time: Elution Start Power, halfway to
  100%, then 100%. Most of the eluate drips through at low power; full power only at the end.

Ends at elution. HRC inhibitor removal (kit step 14) is done off-deck.
"""

from opentrons import protocol_api, types

metadata = {
    "protocolName": "ZymoBIOMICS 96 DNA Kit - Flex + Vacuum Module (Dutton lab v7)",
    "author": "Tavis Goldwire",
    "description": "Spin-plate DNA extraction on the vacuum manifold, 8-96 samples, through elution.",
}

requirements = {"robotType": "Flex", "apiLevel": "2.30"}

# Labware
CUSTOM = {"namespace": "custom_beta", "version": 3}
RESERVOIR = "nest_12_reservoir_22ml"   
RESERVOIR_MAX = 15_000      # uL per reservoir well
WELL_MARGIN = 1_500         # uL left in each reservoir well after its last draw. Estimate, NOT validated:
                            # the well's V-bottom holds ~0.7 mL below 2 mm
TIPRACK = "opentrons_flex_96_tiprack_1000ul"
ELUTION_TIPRACK = "opentrons_flex_96_tiprack_50ul"

# Volumes, uL per well
BINDING_VOL = 600           # added twice
LOADS = 4                   # lysate + binding buffer is loaded in this many equal parts
WASH1_VOL = 400
WASH2_VOLS = (700, 200)
MIX_VOL = 900
MIX_REPS = 10               # about 2 min, in place of the kit's 2 min vortex (was 6)
AIR_GAP = 20                # not used at elution: 50 uL tips have no room for one

# Flow rates, uL/s per channel: (aspirate, dispense)
RATES = {
    "binding": (80, 150),
    "mix": (150, 150),
    "lysate": (100, 15),    # dispense slower than the membrane drains under load vacuum (was 120)
    "wash": (150, 180),
    "water": (6, 10),       # aspirate was 20, too fast; 6 is the pipette's default for 50 uL tips
}
BLOWOUT_RATE = 100
ELUTION_BLOWOUT_RATE = 10
VISCOUS_DELAY_S = 2
BLOWOUT_DELAY_S = 5         # after dispensing into the spin plate, before blowing out

# Heights, mm
ASP_Z = 0.75                 # above well bottom, every 1000 uL tip aspiration
ELUTION_ASP_Z = 0.75         # water draw with the 50 uL tips (0.2 sealed them on the 1-well trough floor).
                            # NOT dry-run tested in the 12-well reservoir
MIX_DISP_Z = 5              # above well bottom. Was 12: after each 900 uL mix draw the rest sits at
                            # ~10 mm (200 uL lysate) to ~13 mm (400 uL), so 12 mm sprayed into the surface
EXIT_SPEED = 5              # mm/s, pulling the tips out of the sample well after each load draw so less
                            # lysate clings to the outside of the tips and drips as they cross the spin plate
TOP_Z = -5                  # below well top, non-contact dispense and every blow-out
PARK_Z = 5                  # above the sample plate top: where the tips wait out each pull, so they
                            # aren't sitting in the spin plate and any drip lands in their own well
LOAD_Z = 3                  # above the spin plate definition's well bottom, lysate dispense under vacuum.
                            # ZR-96 v2's load height on the same plate and collar (MEMBRANE_Z + 5 + ON_COLLAR_DZ)
ELUTION_Z = 4               # above the definition's well bottom. zymo_96_spin_plate.json puts that
                            # at the lowest point of the plate; if that is the drip nozzle, set this to
                            # (nozzle tip to membrane) + 2 mm, measured on a plate, before a real run

# Gripper
SPACER_GRIP_RAISE = 5       # mm above default grip, clears the manifold rim
MODULE_DROP_X = -1.0        # drops on the vacuum module landed ~1 mm right; shift them left
GRIP_FORCE = 15             # N (Opentrons default for labware)
TRAVEL_Z = 150              # gripper jaw height while carrying the plate to the towel (homes at ~166)
BLOT_Z = 1.5                # plate bottom above the B4 slot surface at contact; lower in 0.5 mm steps.
                            # Referenced to the slot, not the towel: the pad definition's height is not used
BLOT_SPEED = 10             # mm/s, descent onto and lift off the towel
BLOT_CONTACT_S = 10

DRY_SHORT_VAC_S = 5


def add_parameters(p: protocol_api.ParameterContext):
    p.add_str(
        variable_name="run_mode",
        display_name="Run Mode",
        description="Dry runs skip delays and return tips to the rack.",
        default="real",
        choices=[
            {"display_name": "Real run", "value": "real"},
            {"display_name": "Dry run - 5 s vacuums", "value": "dry_short"},
            {"display_name": "Dry run - full vacuums", "value": "dry_full"},
        ],
    )
    p.add_int(
        variable_name="sample_columns",
        display_name="Sample Columns",
        description="Tips, samples and reagent wells in columns 1 to this number. 6 = 48 samples.",
        default=6,
        minimum=1,
        maximum=12,
    )
    p.add_bool(
        variable_name="blot",
        display_name="Blot Spin Plate",
        description="Touch the plate underside to the B4 towel before elution.",
        default=False,
    )
    p.add_int(
        variable_name="lysate_volume",
        display_name="Lysate Volume",
        description="Supernatant per sample well. Kit: up to 400 uL. Sets the 4 load volumes.",
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
        variable_name="elution_incubation",
        display_name="Elution Incubation",
        description="Soak on the membrane before the elution vacuum.",
        default=300,
        minimum=0,
        maximum=600,
        unit="s",
    )
    p.add_int(
        variable_name="pump_power",
        display_name="Pump Power",
        description="Pump duty cycle for every pull except elution. No pressure setpoint.",
        default=100,
        minimum=1,
        maximum=100,
        unit="%",
    )
    # Pull times at Pump Power, each followed by a vent.
    for key, name, description, default in (
        ("load_time", "Load Pull Time", "Pull after each of lysate loads 1-3.", 300),
        ("final_load_time", "Final Load Pull Time", "Pull after the last lysate load.", 600),
        ("wash_time", "Wash Pull Time", "Pull after each of the three washes.", 540),
        ("dry_time", "Membrane Dry Time", "Extra pull after the last wash, to dry the membrane.", 600),
    ):
        p.add_int(
            variable_name=key,
            display_name=name,
            description=description,
            default=default,
            minimum=60,
            maximum=900,
            unit="s",
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
    p.add_int(
        variable_name="elution_start_power",
        display_name="Elution Start Power",
        description="Elution steps up from this power to 100% in three equal steps.",
        default=50,
        minimum=1,
        maximum=100,
        unit="%",
    )
    p.add_int(
        variable_name="elution_time",
        display_name="Elution Vacuum Time",
        description="Total elution pull, split evenly across the three power steps.",
        default=240,
        minimum=60,
        maximum=900,
        unit="s",
    )


def run(ctx: protocol_api.ProtocolContext):
    p = ctx.params
    dry = p.run_mode != "real"

    # ---------------- Deck ----------------
    chute = ctx.load_waste_chute()
    vm = ctx.load_module("vacuumModuleV1", "A3")
    collar = vm.load_adapter("opentrons_vacuum_manifold_collar_tall")
    spin_plate = collar.load_labware("zymo_96_spin_plate", "Zymo-Spin I-96-Z Plate", **CUSTOM)
    spacer = ctx.load_adapter("custom_vacuum_manifold_spacer_tall", "D2", **CUSTOM)
    elution_plate = spacer.load_labware("elution_plate_placeholder", "Elution plate", **CUSTOM)
    samples = ctx.load_labware("nest_96_wellplate_2ml_deep", "A2", "Samples")["A1"]
    temp_mod = ctx.load_module("temperatureModuleV2", "C1")
    water_adapter = temp_mod.load_adapter("opentrons_universal_flat_adapter")

    tip_adapters = {s: ctx.load_adapter("opentrons_flex_96_tiprack_adapter", s) for s in ("A1", "B1", "D1")}
    racks = [adapter.load_labware(TIPRACK) for adapter in tip_adapters.values()]
    elution_tips = ctx.load_labware(ELUTION_TIPRACK, "C4", "50 uL tips for elution")
    pad = ctx.load_labware("dutton_blot_pad", "B4", "Blot towel", **CUSTOM) if p.blot else None

    pip = ctx.load_instrument("flex_96channel_1000", "left", tip_racks=racks)  # full pickup: A1 = whole plate

    n = p.sample_columns

    def trough(slot, name, color, per_tip_ul, on=None):
        """12-well reservoir. Each tip column draws from its own well, 8 tips at a time, so
        wells 1-n get everything that column's tips take over the run, plus WELL_MARGIN.
        on: an adapter to load the reservoir onto instead of the bare slot."""
        reservoir = on.load_labware(RESERVOIR, name) if on else ctx.load_labware(RESERVOIR, slot, name)
        fill = 8 * per_tip_ul + WELL_MARGIN
        if fill > RESERVOIR_MAX:
            raise ValueError(f"{name} needs {fill} uL per well; the reservoir holds {RESERVOIR_MAX}.")
        liquid = ctx.define_liquid(name, "ZymoBIOMICS", color)
        for well in reservoir.wells()[:n]:
            well.load_liquid(liquid, fill)
        ctx.comment(f"Setup: {slot} {name}: {fill / 1000:.1f} mL in each of wells A1-A{n}")
        return reservoir["A1"]   # full pickup: aspirating at A1 puts tip column k in well k

    binding = trough("B2", "DNA Binding Buffer", "#FF0000", 2 * BINDING_VOL)
    wash1 = trough("B3", "DNA Wash Buffer 1", "#FFFB00", WASH1_VOL)
    wash2 = trough("C2", "DNA Wash Buffer 2", "#00FF6E", sum(WASH2_VOLS))
    water = trough("C1", "Nuclease-free water", "#0048FF", p.elution_volume, on=water_adapter)
    lysate = ctx.define_liquid("Clarified lysate", "Operator-loaded", "#B266FF")
    for column in samples.parent.columns()[:n]:
        for well in column:
            well.load_liquid(lysate, p.lysate_volume)
    load_vol = (p.lysate_volume + 2 * BINDING_VOL) / LOADS  # every load takes the same share
    ctx.comment(f"Setup: A2 Samples: {p.lysate_volume} uL clarified lysate per well")
    ctx.comment(
        f"{n} sample columns ({8 * n} samples): every tip rack holds tips in columns 1-{n} only. "
        f"Seal spin-plate columns {n + 1}-12." if n < 12 else "Full plate: 96 samples, full tip racks."
    )

    # ---------------- Helpers ----------------
    def hold(seconds):
        if not dry and seconds > 0:
            ctx.delay(seconds=seconds)

    def pull(seconds):
        """Pump at Pump Power for `seconds` (no pressure setpoint), then vent."""
        if p.run_mode == "dry_short":
            seconds = DRY_SHORT_VAC_S
        vm.close_vent()
        task = vm.start_set_vacuum_power(p.pump_power, seconds, vent_after=True, equalize_timeout_s=20)
        ctx.wait_for_tasks([task])

    def pump_on():
        """Pump at Pump Power with no end time; the protocol keeps running. End with pump_off()."""
        vm.close_vent()
        return vm.start_set_vacuum_power(p.pump_power)

    def pump_off(task):
        # Stops the pump without venting, as in ZR-96 v2 (worked on the ZR-96 cleanup run).
        vm.stop_vacuum_pump()
        ctx.wait_for_tasks([task])

    def elution_vacuum(seconds):
        """Step the pump from Elution Start Power to 100% in three equal steps, then vent.
        No vent between steps, the same back-to-back pattern as v7's first run."""
        if p.run_mode == "dry_short":
            seconds = 3 * DRY_SHORT_VAC_S
        start = p.elution_start_power
        powers = (start, (start + 100) // 2, 100)
        step = seconds // 3
        vm.close_vent()
        for power in powers[:-1]:
            ctx.wait_for_tasks([vm.start_set_vacuum_power(power, step)])
        task = vm.start_set_vacuum_power(
            powers[-1], seconds - 2 * step, vent_after=True, equalize_timeout_s=20
        )
        ctx.wait_for_tasks([task])

    def park():
        pip.move_to(samples.top(PARK_Z))

    def set_rates(name):
        pip.flow_rate.aspirate, pip.flow_rate.dispense = RATES[name]

    def discard_tip():
        if dry:
            pip.return_tip()
        else:
            pip.drop_tip(chute)

    def add(volume, source, dest, viscous=False, dest_z=None, blow_out=True, slow_exit=False):
        # The air gap is in the tip too, so it is dispensed back out with the liquid.
        # dest_z: dispense that far above dest's bottom instead of from the top. The blow-out
        # stays at the top either way, above anything still pooled.
        # blow_out=False: no blow-out and no push-out, for liquid that is mixed afterwards.
        # slow_exit: leave the source well at EXIT_SPEED before the air gap.
        pip.aspirate(volume, source.bottom(ASP_Z))
        if viscous:
            hold(VISCOUS_DELAY_S)
        if slow_exit:
            pip.move_to(source.top(), speed=EXIT_SPEED)
        pip.air_gap(AIR_GAP)
        target = dest.top(TOP_Z) if dest_z is None else dest.bottom(dest_z)
        if not blow_out:
            pip.dispense(volume + AIR_GAP, target, push_out=0)
            return
        pip.dispense(volume + AIR_GAP, target)
        if dest.parent is spin_plate:
            hold(BLOWOUT_DELAY_S)
        pip.blow_out(dest.top(TOP_Z))

    def blot():
        """Grip the spin plate in the docked collar, lower it slowly onto the B4 towel,
        lift it, and set it back in the collar. The gripper never lets go on the towel."""
        a1, h12 = spin_plate["A1"].center().point, spin_plate["H12"].center().point
        bottom = spin_plate.calibrated_offset.z
        grip_height = (spin_plate.highest_z - bottom) / 2  # same grip height move_labware uses
        grip = types.Point((a1.x + h12.x) / 2, (a1.y + h12.y) / 2, bottom + grip_height)

        pad_xy = pad["A1"].center().point
        slot_surface_z = pad.calibrated_offset.z  # B4 slot surface (labware origin)
        touch = types.Point(pad_xy.x, pad_xy.y, slot_surface_z + BLOT_Z + grip_height)
        above_grip = grip._replace(z=TRAVEL_Z)
        above_pad = touch._replace(z=TRAVEL_Z)

        def go(point, speed=None):
            ctx.robot.move_to("gripper", types.Location(point, None), speed=speed)

        # Every lateral move happens at TRAVEL_Z: straight up out of the collar, across, straight down.
        ctx.robot.open_gripper_jaw()
        go(above_grip)
        go(grip)
        ctx.robot.close_gripper_jaw(GRIP_FORCE)
        go(above_grip)
        go(above_pad)
        go(touch, BLOT_SPEED)
        hold(BLOT_CONTACT_S)
        go(above_pad, BLOT_SPEED)
        go(above_grip)
        go(grip, BLOT_SPEED)
        ctx.robot.open_gripper_jaw()
        go(above_grip)

    # ---------------- 1. Binding buffer + mix ----------------
    # One blow-out, at the end. Every dispense before it uses push_out=0: a push-out leaves the
    # plunger past its bottom, and the next aspirate then lifts the tips out of the well to reset
    # it (the "mix, blow out, mix" seen on the robot). Opentrons' own mix() does the same.
    pip.pick_up_tip()
    pip.flow_rate.blow_out = BLOWOUT_RATE
    set_rates("binding")
    for _ in range(2):
        add(BINDING_VOL, binding, samples, viscous=True, blow_out=False)

    set_rates("mix")
    for _ in range(MIX_REPS):
        pip.aspirate(MIX_VOL, samples.bottom(ASP_Z))
        pip.dispense(MIX_VOL, samples.bottom(MIX_DISP_Z), push_out=0)
    pip.blow_out(samples.top(TOP_Z))

    # ---------------- 2. Load spin plate in 4 parts, pump on while dispensing ----------------
    # The pump starts before the aspirate so it is pulling by the time the tips reach the plate.
    set_rates("lysate")
    for i in range(LOADS):
        load_task = pump_on()
        add(load_vol, samples, spin_plate["A1"], viscous=True, dest_z=LOAD_Z, slow_exit=True)
        park()
        pump_off(load_task)
        pull(p.final_load_time if i == LOADS - 1 else p.load_time)
    discard_tip()

    # ---------------- 3. Wash 1 ----------------
    pip.pick_up_tip()
    set_rates("wash")
    add(WASH1_VOL, wash1, spin_plate["A1"])
    discard_tip()
    pull(p.wash_time)

    # ---------------- 4. Wash 2 (x2) + dry ----------------
    # Heat the elution water from here: about 30 min before it's used, so it warms through the
    # plastic without evaporating for the whole run. Skipped in 5 s dry runs (they'd wait on it).
    heat = p.elution_temp > 0 and p.run_mode != "dry_short"
    if heat:
        temp_mod.start_set_temperature(p.elution_temp)
    pip.pick_up_tip()
    set_rates("wash")
    add(WASH2_VOLS[0], wash2, spin_plate["A1"])
    park()  # over the now-empty sample plate, not the shared Wash 2 trough
    pull(p.wash_time)
    add(WASH2_VOLS[1], wash2, spin_plate["A1"])
    discard_tip()
    pull(p.wash_time)
    pull(p.dry_time)

    # ---------------- 5. Blot, stack for elution, swap tips ----------------
    ctx.move_labware(collar, vm.manifold_dock, use_gripper=True)
    if pad:
        blot()
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

    # Dry runs returned their tips to the D1 rack: park it in D2 (empty now the spacer has moved).
    ctx.move_labware(racks[-1], "D2" if dry else chute, use_gripper=True)
    ctx.move_labware(elution_tips, tip_adapters["D1"], use_gripper=True)

    # ---------------- 6. Elution ----------------
    pip.pick_up_tip(elution_tips["A1"])
    set_rates("water")
    pip.flow_rate.blow_out = ELUTION_BLOWOUT_RATE
    if heat:
        temp_mod.await_temperature(p.elution_temp)  # the module, not the water: see the docstring
    pip.aspirate(p.elution_volume, water.bottom(ELUTION_ASP_Z))
    pip.dispense(p.elution_volume, spin_plate["A1"].bottom(ELUTION_Z))
    hold(BLOWOUT_DELAY_S)
    pip.blow_out(spin_plate["A1"].bottom(ELUTION_Z))
    discard_tip()
    if heat:
        temp_mod.deactivate()

    hold(p.elution_incubation)
    elution_vacuum(p.elution_time)
    ctx.comment("Done. Next, off-deck: HRC plate, 3,500 x g for 3 min (kit step 14).")
