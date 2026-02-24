from opentrons import protocol_api

metadata = {
    'protocolName': 'ZR-96 DNA Clean & Concentrator-5 Protocol V9',
    'author': 'OpentronsAI',
    'description': 'DNA binding buffer transfer, wash buffer addition, and water elution with separate dispense heights',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_int(
        variable_name="sample_volume",
        display_name="Sample Volume",
        description="Volume of sample in each well (µL)",
        default=50,
        minimum=0,
        maximum=100
    )
    
    parameters.add_int(
        variable_name="water_volume",
        display_name="Water Volume",
        description="Volume of DNase-free water to add to each well (µL)",
        default=15,
        minimum=10,
        maximum=20
    )

def run(protocol: protocol_api.ProtocolContext):
    # Access runtime parameters
    sample_vol = protocol.params.sample_volume
    water_vol = protocol.params.water_volume
    
    # Calculate binding buffer volume based on sample volume
    if sample_vol <= 50:
        binding_buffer_vol = 100
    else:
        binding_buffer_vol = 2 * sample_vol
    
    # Load labware
    reservoir = protocol.load_labware('nest_12_reservoir_15ml', 5, 'Reagent Reservoir')
    pcr_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 2, 'PCR Plate with Samples')
    deep_well_plate = protocol.load_labware('zymo_spin_on_pcr', 1, 'Deep Well Plate')
    deep_well_plate_balance = protocol.load_labware('zymo_spin_on_pcr', 10, 'Deep Well Plate Balance')
    reservoir_balance = protocol.load_labware('nest_12_reservoir_15ml', 7, 'Water Reservoir for Centrifuge Balance')
    
    # Load tip racks
    tips_200_1 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 4)
    tips_200_2 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 8)
    # tips_200_3 = protocol.load_labware('opentrons_96_filtertiprack_200ul', 9)
    tips_20 = protocol.load_labware('opentrons_96_filtertiprack_20ul', 11)
    
    # Load pipettes
    p300_multi = protocol.load_instrument('p300_multi_gen2', 'left', tip_racks=[tips_200_1, tips_200_2])
    p20_multi = protocol.load_instrument('p20_multi_gen2', 'right', tip_racks=[tips_20])
    
    # Define reagent locations
    binding_buffer_wells = [reservoir['A1'], reservoir['A2']]
    water_well = reservoir['A12']
    wash_buffer_wells = [reservoir['A4'], reservoir['A5'], reservoir['A6']]
    balance_water_wells = [reservoir_balance['A1'], reservoir_balance['A2'], reservoir_balance['A3'], 
                          reservoir_balance['A4'], reservoir_balance['A5'], reservoir_balance['A6'], 
                          reservoir_balance['A7']]

    # Define liquids for plate map
    binding_buffer_liquid = protocol.define_liquid(
        name="DNA Binding Buffer",
        description="DNA Binding Buffer for sample processing",
        display_color="#FF6600"
    )
    
    wash_buffer_liquid = protocol.define_liquid(
        name="DNA Wash Buffer", 
        description="DNA Wash Buffer for cleaning",
        display_color="#0066FF"
    )
    
    water_liquid = protocol.define_liquid(
        name="DNase-free Water",
        description="DNase-free water for elution",
        display_color="#00FFFF"
    )
    
    sample_liquid = protocol.define_liquid(
        name="DNA Sample",
        description=f"DNA samples ({sample_vol} µL each)",
        display_color="#00FF00"
    )

    balance_water_liquid = protocol.define_liquid(
        name="Water",
        description="Water used for balance (get from sink)",
        display_color="#0000FF"
    )
    
    # Load liquids into labware
    for well in binding_buffer_wells:
        well.load_liquid(liquid=binding_buffer_liquid, volume=5000)
    
    wash_volumes = [12660, 12660, 12660]
    for well, vol in zip(wash_buffer_wells, wash_volumes):
        well.load_liquid(liquid=wash_buffer_liquid, volume=vol)
    
    water_well.load_liquid(liquid=water_liquid, volume=1800)
    
    for well in pcr_plate.wells():
        well.load_liquid(liquid=sample_liquid, volume=sample_vol)

    balance_water_volumes = [11000, 11000, 13000, 13000, 13000, 13000, 13000]
    for well, vol in zip(balance_water_wells, balance_water_volumes):
        well.load_liquid(liquid=balance_water_liquid, volume=vol)
    
    protocol.comment(f"Starting ZR-96 DNA Clean & Concentrator-5 Protocol")
    protocol.comment(f"Sample volume: {sample_vol} µL")
    protocol.comment(f"Binding buffer volume: {binding_buffer_vol} µL")
    protocol.comment(f"Water volume: {water_vol} µL")
   
    
    # Step 1: Transfer DNA Binding Buffer and mix samples
    protocol.comment("Step 1: Adding DNA Binding Buffer to samples")
    
    for i, column in enumerate(pcr_plate.columns()):
        # Pick up tip for binding buffer addition and mixing
        p300_multi.pick_up_tip()
        
        # Alternate between wells A1 and A2 for binding buffer
        source_well = binding_buffer_wells[i % 2]
        
        # Transfer binding buffer to PCR plate
        p300_multi.aspirate(binding_buffer_vol, source_well)
        p300_multi.dispense(binding_buffer_vol, column[0])
        
        # Mix 10 times
        mix_volume = min((sample_vol + binding_buffer_vol) * 0.8, 200)
        p300_multi.mix(10, mix_volume, column[0])
        
        # Drop tip after mixing
        # p300_multi.drop_tip()
        
        # Pick up new tip for transfer to deep well plate
        # p300_multi.pick_up_tip()
        
        # Transfer mixed solution to deep well plate at stacked plate height
        p300_multi.aspirate(sample_vol + binding_buffer_vol, column[0])
        p300_multi.dispense(sample_vol + binding_buffer_vol, 
                           deep_well_plate.columns()[i][0])
        protocol.delay(seconds=2)
        p300_multi.blow_out(deep_well_plate.columns()[i][0])
        
        # Drop tip after transfer to deep well plate
        p300_multi.drop_tip()
    
    # Add water to the balance plate at stacked plate height
    p300_multi.pick_up_tip()
    for i, column in enumerate(deep_well_plate_balance.columns()):
        source_well = balance_water_wells[i % len(balance_water_wells)]
        
        p300_multi.aspirate(binding_buffer_vol + sample_vol, source_well)
        p300_multi.dispense(binding_buffer_vol + sample_vol, 
                           column[0])

    p300_multi.drop_tip()

    # Pause for centrifugation
    protocol.pause("Remove the deep well sample plate and balance plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 2: First wash buffer addition (300 µL in two 150 µL increments)
    protocol.comment("Step 2: Adding first wash buffer (300 µL total)")
    p300_multi.pick_up_tip()
    
    # First 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)
        p300_multi.blow_out(column[0])
    
    # Second 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()

    # Prepare the second centrifuge balance
    protocol.comment("Step 2 Continued: Building centrifuge balance")
    balance_water_600_wells = [reservoir_balance.wells_by_name()[f"A{i}"] for i in range(3, 8)]
    p300_multi.pick_up_tip()

    # First 150 µL addition
    for i, column in enumerate(deep_well_plate_balance.columns()):
        balance_water_source = balance_water_600_wells[i % len(balance_water_600_wells)]
        p300_multi.aspirate(150, balance_water_source)
        p300_multi.dispense(150, column[0])
        p300_multi.blow_out(column[0])

    # Second 150 µL addition
    for i, column in enumerate(deep_well_plate_balance.columns()):
        balance_water_source = balance_water_600_wells[i % len(balance_water_600_wells)]
        p300_multi.aspirate(150, balance_water_source)
        p300_multi.dispense(150, column[0])
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()

    # Pause for centrifugation
    protocol.pause("Remove the deep well sample plate and balance plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 3: Second wash buffer addition (300 µL in two 150 µL increments)
    protocol.comment("Step 3: Adding second wash buffer (300 µL total)")
    p300_multi.pick_up_tip()
    
    # First 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)
        p300_multi.blow_out(column[0])
    
    # Second 150 µL wash
    for i, column in enumerate(deep_well_plate.columns()):
        wash_source = wash_buffer_wells[i % len(wash_buffer_wells)]
        p300_multi.aspirate(150, wash_source)
        p300_multi.dispense(150, column[0])
        protocol.delay(seconds=1)
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()

    # Prepare the third centrifuge balance
    protocol.comment("Step 3 Continued: Building centrifuge balance")
    balance_water_600_wells = [reservoir_balance.wells_by_name()[f"A{i}"] for i in range(3, 8)]
    p300_multi.pick_up_tip()

    # First 150 µL addition
    for i, column in enumerate(deep_well_plate_balance.columns()):
        balance_water_source = balance_water_600_wells[i % len(balance_water_600_wells)]
        p300_multi.aspirate(150, balance_water_source)
        p300_multi.dispense(150, column[0])
        p300_multi.blow_out(column[0])

    # Second 150 µL addition
    for i, column in enumerate(deep_well_plate_balance.columns()):
        balance_water_source = balance_water_600_wells[i % len(balance_water_600_wells)]
        p300_multi.aspirate(150, balance_water_source)
        p300_multi.dispense(150, column[0])
        p300_multi.blow_out(column[0])
    
    p300_multi.drop_tip()
    
    # Pause for centrifugation
    protocol.comment("You must add the 300 µL to each well in columns 4-12 of the sample spin plate by hand!")
    protocol.pause("Remove the deep well sample and balance plate, centrifuge, and place back on the OT-2. Resume when ready.")
    
    # Step 4: Add DNase-free water
    protocol.comment(f"Step 4: Adding {water_vol} µL of DNase-free water to each well")
    
    p20_multi.pick_up_tip()
    for column in deep_well_plate.columns():
        p20_multi.aspirate(water_vol, water_well)
        p20_multi.dispense(water_vol, column[0])
    p20_multi.drop_tip()
    
    protocol.comment("Protocol complete! All steps finished successfully.")
    
    # Display reagent setup information
    protocol.comment("=== REAGENT SETUP GUIDE ===")
    protocol.comment(f"Reservoir Well A1: 5000 µL DNA Binding Buffer")
    protocol.comment(f"Reservoir Well A2: 5000 µL DNA Binding Buffer") 
    protocol.comment(f"Reservoir Wells A4-A6: 12,600 µL DNA Wash Buffer each")
    protocol.comment(f"Reservoir Well A12: 1800 µL DNase-free Water")
    protocol.comment(f"Balance Reservoir Well A1-2: 11000 µL DNase-free Water")
    protocol.comment(f"Balance Reservoir Well A3-7: 13000 µL DNase-free Water")
    protocol.comment(f"PCR Plate: {sample_vol} µL DNA sample in each well")
