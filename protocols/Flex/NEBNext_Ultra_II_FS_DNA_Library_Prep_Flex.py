from opentrons import protocol_api
from opentrons import types

metadata = {
    'protocolName': 'NEBNext® Ultra™ II FS DNA Library Prep (Section 2: Inputs >= 100ng)',
    'author': 'Dutton Lab (Verified against NEB Manual Sec 2)',
    'description': 'Full NEBNext Ultra II FS Lib Prep. '
                   'Optimized for Flex: 4x p50 Racks with Manual Override Tip Logic.'
}

requirements = {
    'robotType': 'Flex',
    'apiLevel': '2.20'
}

def add_parameters(parameters: protocol_api.Parameters):
    parameters.add_str(
        variable_name="SAMPLES",
        display_name="Number of Samples",
        description="Select sample count.",
        default="24x",
        choices=[
            {"display_name": "8 Samples (1 col)", "value": "8x"},
            {"display_name": "16 Samples (2 cols)", "value": "16x"},
            {"display_name": "24 Samples (3 cols)", "value": "24x"},
        ]
    )
    
    parameters.add_int(
        variable_name="FRAG_TIME",
        display_name="Fragmentation Time (min)",
        description="Time at 37C for fragmentation.",
        default=15,
        choices=[
            {"display_name": "5 min", "value": 5},
            {"display_name": "10 min", "value": 10},
            {"display_name": "15 min", "value": 15},
            {"display_name": "20 min", "value": 20},
            {"display_name": "30 min", "value": 30},
            {"display_name": "35 min", "value": 35},
            {"display_name": "40 min", "value": 40},
        ]
    )
    
    parameters.add_int(
        variable_name="PCR_CYCLES",
        display_name="PCR Cycles",
        description="Number of PCR cycles.",
        default=4,
        choices=[
            {"display_name": "3 Cycles", "value": 3},
            {"display_name": "4 Cycles", "value": 4},
            {"display_name": "5 Cycles", "value": 5},
            {"display_name": "6 Cycles", "value": 6},
            {"display_name": "7 Cycles", "value": 7},
            {"display_name": "8 Cycles", "value": 8},
            {"display_name": "10 Cycles", "value": 10},
            {"display_name": "12 Cycles", "value": 12},
        ]
    )
    
    parameters.add_bool(
        variable_name="DRYRUN",
        display_name="Dry Run",
        description="Execute movements without pauses or temperature steps.",
        default=False
    )

def run(protocol: protocol_api.ProtocolContext):

    # ── PARAMETERS ───────────────────────────────────────────────────
    SAMPLES = protocol.params.SAMPLES
    FRAG_TIME = protocol.params.FRAG_TIME
    PCR_CYCLES = protocol.params.PCR_CYCLES
    DRYRUN = protocol.params.DRYRUN

    waste_chute = protocol.load_waste_chute()

    # ── LABWARE ──────────────────────────────────────────────────────
    thermocycler = protocol.load_module('thermocyclerModuleV2')
    sample_plate = thermocycler.load_labware('nest_96_wellplate_100ul_pcr_full_skirt')

    mag_block = protocol.load_module('magneticBlockV1', 'D1')
    MAG_STAGING_SLOT = 'A2' 

    temp_block = protocol.load_module('temperature module gen2', 'C1')
    reagent_block = temp_block.load_labware('opentrons_24_aluminumblock_nest_1.5ml_snapcap')

    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 'D2')

    # p50 Tips
    tips50_1 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'B3', 'Rack 1')
    tips50_2 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'A3', 'Rack 2')
    tips50_3 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'A4', 'Rack 3 (Staged)')
    tips50_4 = protocol.load_labware('opentrons_flex_96_tiprack_50ul', 'B4', 'Rack 4 (Staged)')
    
    # p1000 Tips
    tips1000_1 = protocol.load_labware('opentrons_flex_96_tiprack_1000ul', 'C2')
    tips1000_2 = protocol.load_labware('opentrons_flex_96_tiprack_1000ul', 'C3')
    tips1000_3 = protocol.load_labware('opentrons_flex_96_tiprack_1000ul', 'C4')  # staged

    p1000 = protocol.load_instrument('flex_8channel_1000', 'left')  # Manual tip tracking
    p50 = protocol.load_instrument('flex_8channel_50', 'right') # No auto tip racks assigned

    # ── TIP TRACKING (MANUAL SYSTEM) ─────────────────────────────────
    _p1000_cols_used = 0
    p50_total_cols_used = 0
    
    # Current logical pointers
    active_rack_A = tips50_1 # Physically in B3
    active_rack_B = tips50_2 # Physically in A3
    staged_rack_C = tips50_3 # In A4
    staged_rack_D = tips50_4 # In B4

    def get_p50_tip_location(mode='ALL'):
        nonlocal p50_total_cols_used
        
        # Determine which rack to use
        if p50_total_cols_used < 12:
            rack = active_rack_A
            col_index = p50_total_cols_used
        elif p50_total_cols_used < 24:
            rack = active_rack_B
            col_index = p50_total_cols_used - 12
        elif p50_total_cols_used == 24:
            protocol.comment("⚠️ SWAP: B3->B2, A4->B3")
            protocol.move_labware(active_rack_A, 'B2', use_gripper=True)
            protocol.move_labware(staged_rack_C, 'B3', use_gripper=True)
            rack = staged_rack_C
            col_index = 0
        elif p50_total_cols_used < 36:
            rack = staged_rack_C
            col_index = p50_total_cols_used - 24
        elif p50_total_cols_used == 36:
            protocol.comment("⚠️ SWAP: A3->D4, B4->A3")
            protocol.move_labware(active_rack_B, 'D4', use_gripper=True)
            protocol.move_labware(staged_rack_D, 'A3', use_gripper=True)
            rack = staged_rack_D
            col_index = 0
        else:
            rack = staged_rack_D
            col_index = p50_total_cols_used - 36
            
        p50_total_cols_used += 1
        
        if mode == 'SINGLE':
            return rack.wells()[col_index * 8] # Return A nozzle well for start="A1"
        else:
            return rack.wells()[col_index * 8] # Return A nozzle well (start of col)

    def get_p1000_tip(mode='ALL'):
        """Manual p1000 tip tracker. Burns 1 col per pick (SINGLE or ALL).
        C2 (12 cols) → C3 (12 cols) → swap: trash C2, move C4→C2 → C4 (12 cols)"""
        nonlocal _p1000_cols_used

        if _p1000_cols_used < 12:
            rack = tips1000_1          # C2
            col = _p1000_cols_used
        elif _p1000_cols_used < 24:
            rack = tips1000_2          # C3
            col = _p1000_cols_used - 12
        else:
            if _p1000_cols_used == 24:
                protocol.comment("⚠️ p1000 SWAP: C2→waste chute, C4→C2")
                protocol.move_labware(tips1000_1, waste_chute, use_gripper=True)
                protocol.move_labware(tips1000_3, 'C2', use_gripper=True)
            rack = tips1000_3          # was C4, now physically in C2
            col = _p1000_cols_used - 24

        _p1000_cols_used += 1
        return rack.wells()[col * 8]   # A-row well (works for both ALL and SINGLE A1)

    # ── LIQUIDS ──────────────────────────────────────────────────────
    liq_erat = protocol.define_liquid(name="ERAT", description="Enzyme", display_color="#FF0000")
    liq_adapt = protocol.define_liquid(name="Adaptor", description="Adaptor", display_color="#0000FF")
    liq_lig = protocol.define_liquid(name="LigMM", description="Master Mix", display_color="#FFA500")
    liq_user = protocol.define_liquid(name="USER", description="Enzyme", display_color="#800080")
    liq_primer = protocol.define_liquid(name="Primers", description="Indices", display_color="#008080")
    liq_q5 = protocol.define_liquid(name="Q5MM", description="PCR Mix", display_color="#FF00FF")
    liq_beads = protocol.define_liquid(name="Beads", description="AMPure", display_color="#8B4513")
    liq_etoh = protocol.define_liquid(name="EtOH", description="80%", display_color="#00FFFF")
    liq_rsb = protocol.define_liquid(name="RSB", description="0.1X TE", display_color="#FFFF00")
    liq_samples = protocol.define_liquid(name="DNA Samples", description="Input DNA (≥100 ng in 26 µL)", display_color="#00FF00")

    ERAT = reagent_block['A1']; ERAT.load_liquid(liq_erat, 260)
    LIG_MM = reagent_block['A2']; LIG_MM.load_liquid(liq_lig, 900)
    Q5_MM = reagent_block['A3']; Q5_MM.load_liquid(liq_q5, 700)
    ADAPTOR = reagent_block['A4']; ADAPTOR.load_liquid(liq_adapt, 75)
    USER = reagent_block['A5']; USER.load_liquid(liq_user, 80)
    P_WELLS = [reagent_block['A6'], reagent_block['B1'], reagent_block['B2']]
    for pw in P_WELLS: pw.load_liquid(liq_primer, 100)

    BEADS = reservoir['A1']; BEADS.load_liquid(liq_beads, 3000)
    ETOH = reservoir['A4']; ETOH.load_liquid(liq_etoh, 12000)
    RSB = reservoir['A6']; RSB.load_liquid(liq_rsb, 2000)
    TRASH = reservoir['A12']

    # ── LOGIC ────────────────────────────────────────────────────────
    if SAMPLES == '8x': start_cols = ['A1']; dest_cols = ['A2']
    elif SAMPLES == '16x': start_cols = ['A1', 'A3']; dest_cols = ['A2', 'A4']
    else: start_cols = ['A1', 'A3', 'A5']; dest_cols = ['A2', 'A4', 'A6']

    # Load sample liquids into plate so they appear on the Opentrons setup screen
    for col_n in start_cols:
        col_wells = sample_plate.columns_by_name()[col_n[1:]]
        for well in col_wells:
            well.load_liquid(liq_samples, 26)

    plate_loc = 'thermocycler'
    def move_plate(target):
        nonlocal plate_loc
        if plate_loc == target: return
        if plate_loc == 'thermocycler': thermocycler.open_lid()
        loc = thermocycler if target == 'thermocycler' else mag_block if target == 'magnet' else MAG_STAGING_SLOT
        protocol.move_labware(sample_plate, loc, use_gripper=True)
        if target == 'thermocycler': thermocycler.close_lid()
        plate_loc = target

    def bead_loc(well, height_type):
        if height_type == 'bead': return well.bottom(0.5) 
        elif height_type == 'sup': return well.bottom(3.0).move(types.Point(x=0.5, y=0, z=0))
        return well.bottom(10)

    # ── CORE FUNCTIONS ───────────────────────────────────────────────
    def distribute_single(pip, source, vol, dest_list, mix_v=0):
        pip.configure_nozzle_layout(style=protocol_api.SINGLE, start="A1")
        if pip == p50:
            tip = get_p50_tip_location(mode='SINGLE')
        else:
            tip = get_p1000_tip(mode='SINGLE')
        pip.pick_up_tip(tip)
        
        for col_n in dest_list:
            wells = sample_plate.columns_by_name()[col_n[1:]]
            needed = vol * 8 * 1.1
            if needed <= pip.max_volume:
                if mix_v > 0: pip.mix(3, mix_v, source)
                pip.aspirate(needed, source, rate=0.5)
                for w in wells: pip.dispense(vol, w, rate=0.5)
                pip.blow_out(source.top())
            else:
                half = vol * 4 * 1.1
                for chunk in [wells[:4], wells[4:]]:
                    if mix_v > 0: pip.mix(2, mix_v, source)
                    pip.aspirate(half, source, rate=0.5)
                    for w in chunk: pip.dispense(vol, w, rate=0.5)
                    pip.blow_out(source.top())
        pip.drop_tip()
        pip.configure_nozzle_layout(style=protocol_api.ALL)

    # ── RUN ──────────────────────────────────────────────────────────
    if not DRYRUN:
        thermocycler.set_block_temperature(4)
        thermocycler.set_lid_temperature(75)  # Per NEB 2.1.5; PCR later sets to 105
        temp_block.set_temperature(4)

    # 1. ERAT
    move_plate('staging')
    distribute_single(p50, ERAT, 9, start_cols, mix_v=20)
    for col_n in start_cols:
        p50.pick_up_tip(get_p50_tip_location())
        p50.mix(10, 20, sample_plate[col_n])
        p50.drop_tip()

    move_plate('thermocycler')
    if not DRYRUN:
        thermocycler.execute_profile(steps=[{'temperature': 37, 'hold_time_minutes': FRAG_TIME}, {'temperature': 65, 'hold_time_minutes': 30}], repetitions=1, block_max_volume=50)

    # 2. LIGATION
    move_plate('staging')
    distribute_single(p50, ADAPTOR, 2.5, start_cols)
    distribute_single(p1000, LIG_MM, 31, start_cols, mix_v=50)
    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip())
        p1000.mix(15, 40, sample_plate[col_n], rate=0.5)
        p1000.drop_tip()

    move_plate('thermocycler')
    if not DRYRUN: 
        thermocycler.open_lid()
        thermocycler.set_block_temperature(20, hold_time_minutes=15)

    # USER
    move_plate('staging')
    distribute_single(p50, USER, 3, start_cols)
    for col_n in start_cols:
        p50.pick_up_tip(get_p50_tip_location())
        p50.mix(5, 30, sample_plate[col_n])
        p50.drop_tip()
    
    move_plate('thermocycler')
    if not DRYRUN: 
        thermocycler.set_lid_temperature(47); thermocycler.close_lid()
        thermocycler.set_block_temperature(37, hold_time_minutes=15)

    # 3. SIZE SELECTION
    move_plate('staging')
    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip())
        p1000.aspirate(28.5, RSB) # RSB as TE
        p1000.dispense(28.5, sample_plate[col_n])
        p1000.mix(5, 60, sample_plate[col_n]); p1000.drop_tip()

    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip()); p1000.mix(5, 100, BEADS)
        p1000.aspirate(40, BEADS, rate=0.5); p1000.dispense(40, sample_plate[col_n])
        p1000.mix(10, 100, sample_plate[col_n]); p1000.drop_tip()

    if not DRYRUN: protocol.delay(minutes=5)
    move_plate('magnet')
    if not DRYRUN: protocol.delay(minutes=5)

    for s, d in zip(start_cols, dest_cols):
        p1000.pick_up_tip(get_p1000_tip()); p1000.aspirate(140, bead_loc(sample_plate[s], 'sup'), rate=0.1)
        p1000.dispense(140, sample_plate[d]); p1000.drop_tip()

    move_plate('staging')
    for col_n in dest_cols:
        p50.pick_up_tip(get_p50_tip_location()); p50.mix(3, 20, BEADS)
        p50.aspirate(20, BEADS); p50.dispense(20, sample_plate[col_n]); p50.drop_tip()
        p1000.pick_up_tip(get_p1000_tip()); p1000.mix(10, 130, sample_plate[col_n]); p1000.drop_tip()

    if not DRYRUN: protocol.delay(minutes=5)
    move_plate('magnet')
    if not DRYRUN: protocol.delay(minutes=5)

    for col_n in dest_cols:
        p1000.pick_up_tip(get_p1000_tip()); p1000.aspirate(180, bead_loc(sample_plate[col_n], 'sup'), rate=0.1)
        p1000.dispense(180, TRASH); p1000.drop_tip()

    w_tips = {}
    for col_n in dest_cols:
        p1000.pick_up_tip(get_p1000_tip()); w_tips[col_n] = p1000._last_tip_picked_up_from; p1000.return_tip()

    for i in range(2):
        for col_n in dest_cols:
            p1000.pick_up_tip(w_tips[col_n]); p1000.aspirate(200, ETOH)
            p1000.dispense(200, bead_loc(sample_plate[col_n], 'dispense')); p1000.return_tip()
        if not DRYRUN: protocol.delay(seconds=30)
        for col_n in dest_cols:
            p1000.pick_up_tip(w_tips[col_n]); p1000.aspirate(200, bead_loc(sample_plate[col_n], 'sup'))
            p1000.dispense(200, TRASH); p1000.aspirate(20, bead_loc(sample_plate[col_n], 'bead'))
            p1000.dispense(20, TRASH)
            if i == 1: p1000.drop_tip()
            else: p1000.return_tip()

    if not DRYRUN: protocol.delay(minutes=5)  # Air dry beads (NEB 2.3.12)
    move_plate('staging')
    for col_n in dest_cols:
        p50.pick_up_tip(get_p50_tip_location()); p50.aspirate(17, RSB); p50.dispense(17, sample_plate[col_n])
        p50.mix(10, 15, sample_plate[col_n]); p50.drop_tip()

    if not DRYRUN: protocol.delay(minutes=2)
    move_plate('magnet')
    if not DRYRUN: protocol.delay(minutes=5)  # Mag sep after elution (NEB 2.3.15)

    # 4. PCR
    move_plate('staging')
    for s, d in zip(dest_cols, start_cols):
        p50.pick_up_tip(get_p50_tip_location()); p50.aspirate(15, bead_loc(sample_plate[s], 'sup'))
        p50.dispense(15, sample_plate[d]); p50.drop_tip()

    distribute_single(p1000, Q5_MM, 25, start_cols)
    
    p50.configure_nozzle_layout(style=protocol_api.SINGLE, start="A1")
    for i, col_n in enumerate(start_cols):
        col_wells = sample_plate.columns_by_name()[col_n[1:]]  # 8 wells in column
        p50.pick_up_tip(get_p50_tip_location(mode='SINGLE'))
        p50.aspirate(44, P_WELLS[i])
        for w_idx in range(4): p50.dispense(10, col_wells[w_idx])
        p50.aspirate(44, P_WELLS[i])
        for w_idx in range(4, 8): p50.dispense(10, col_wells[w_idx])
        p50.drop_tip()
    p50.configure_nozzle_layout(style=protocol_api.ALL)

    for col_n in start_cols:
        p50.pick_up_tip(get_p50_tip_location()); p50.mix(10, 40, sample_plate[col_n]); p50.drop_tip()

    move_plate('thermocycler')
    if not DRYRUN:
        thermocycler.set_lid_temperature(105); thermocycler.close_lid()
        # Initial denaturation
        thermocycler.execute_profile(
            steps=[{'temperature': 98, 'hold_time_seconds': 30}],
            repetitions=1, block_max_volume=50)
        # Cycling: denaturation + annealing/extension
        thermocycler.execute_profile(
            steps=[{'temperature': 98, 'hold_time_seconds': 10},
                   {'temperature': 65, 'hold_time_seconds': 75}],
            repetitions=PCR_CYCLES, block_max_volume=50)
        # Final extension
        thermocycler.execute_profile(
            steps=[{'temperature': 65, 'hold_time_minutes': 5}],
            repetitions=1, block_max_volume=50)
        thermocycler.set_block_temperature(4)

    # 5. CLEANUP
    move_plate('staging')
    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip()); p1000.mix(5, 50, BEADS)
        p1000.aspirate(45, BEADS); p1000.dispense(45, sample_plate[col_n])
        p1000.mix(10, 80, sample_plate[col_n]); p1000.drop_tip()

    if not DRYRUN: protocol.delay(minutes=5)
    move_plate('magnet')
    if not DRYRUN: protocol.delay(minutes=5)

    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip()); p1000.aspirate(95, bead_loc(sample_plate[col_n], 'sup'))
        p1000.dispense(95, TRASH); p1000.drop_tip()

    w_tips = {}
    for col_n in start_cols:
        p1000.pick_up_tip(get_p1000_tip()); w_tips[col_n] = p1000._last_tip_picked_up_from; p1000.return_tip()

    for i in range(2):
        for col_n in start_cols:
            p1000.pick_up_tip(w_tips[col_n]); p1000.aspirate(200, ETOH)
            p1000.dispense(200, bead_loc(sample_plate[col_n], 'dispense')); p1000.return_tip()
        if not DRYRUN: protocol.delay(seconds=30)
        for col_n in start_cols:
            p1000.pick_up_tip(w_tips[col_n]); p1000.aspirate(200, bead_loc(sample_plate[col_n], 'sup'))
            p1000.dispense(200, TRASH); p1000.aspirate(20, bead_loc(sample_plate[col_n], 'bead'))
            p1000.dispense(20, TRASH)
            if i == 1: p1000.drop_tip()
            else: p1000.return_tip()

    if not DRYRUN: protocol.delay(minutes=5)  # Air dry beads (NEB 2.5.8)
    move_plate('staging')
    for col_n in start_cols:
        p50.pick_up_tip(get_p50_tip_location()); p50.aspirate(33, RSB); p50.dispense(33, sample_plate[col_n])
        p50.mix(10, 25, sample_plate[col_n]); p50.drop_tip()

    if not DRYRUN: protocol.delay(minutes=2)
    move_plate('magnet')
    if not DRYRUN: protocol.delay(minutes=5)  # Mag sep after elution (NEB 2.5.11)

    for s, d in zip(start_cols, dest_cols):
        p50.pick_up_tip(get_p50_tip_location()); p50.aspirate(30, bead_loc(sample_plate[s], 'sup'))
        p50.dispense(30, sample_plate[d]); p50.drop_tip()

    protocol.comment('Protocol Complete')