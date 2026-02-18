from opentrons import protocol_api

metadata = {
    'protocolName': 'Basic Aliquoting with CSV Parameter - Largest to Smallest',
    'author': 'OpentronsAI',
    'description': 'Transfer samples from PCR plate to pooling tube based on uploaded CSV data, sorted from largest to smallest volume',
    'source': 'OpentronsAI'
}

requirements = {
    'robotType': 'OT-2',
    'apiLevel': '2.22'
}

def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="transfer_csv",
        display_name="Transfer CSV File",
        description="CSV file with Well and Volume columns for sample transfers"
    )

def run(protocol: protocol_api.ProtocolContext):
    # Access the uploaded CSV file
    csv_file = protocol.params.transfer_csv
    
    # Parse the CSV data
    csv_data = csv_file.parse_as_csv()
    
    # Skip header row and get transfer data
    transfer_data = list(csv_data)[1:]  # Skip header row
    
    # Sort transfer data by volume (largest to smallest)
    transfer_data.sort(key=lambda row: float(row[1]), reverse=True)
    
    # Load labware
    source_plate = protocol.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt', 1)
    tube_block = protocol.load_labware('opentrons_24_aluminumblock_nest_2ml_screwcap', 2)
    tiprack = protocol.load_labware('opentrons_96_filtertiprack_20ul', 3)
    
    # Load pipette
    p20 = protocol.load_instrument('p20_single_gen2', 'right', tip_racks=[tiprack])
    
    # Define pooling tube (using first position in tube block)
    pooling_tube = tube_block['A1']
    
    # Define liquid for visualization
    sample_liquid = protocol.define_liquid(
        name="Sample",
        description="Sample liquid in PCR plate wells",
        display_color="#FF0000"
    )
    
    # Load liquid into source wells (for visualization)
    for row in transfer_data:
        well_name = row[0]  # First column should be Well
        source_plate[well_name].load_liquid(liquid=sample_liquid, volume=20)
    
    # Perform transfers based on sorted CSV data (largest to smallest volume)
    for row in transfer_data:
        well_name = row[0]  # First column: Well position
        volume = float(row[1])  # Second column: Volume
        
        protocol.comment(f"Transferring {volume} µL from well {well_name}")
        
        # Pick up tip
        p20.pick_up_tip()
        
        # Mix sample briefly (3 times with 15 µL)
        p20.mix(3, 15, source_plate[well_name])
        
        # Transfer specified volume to pooling tube
        p20.transfer(
            volume,
            source_plate[well_name],
            pooling_tube,
            new_tip='never'  # Already have tip
        )
        
        # Drop tip
        p20.drop_tip()
    
    protocol.comment(f"Protocol completed. Transferred samples from {len(transfer_data)} wells to pooling tube in order from largest to smallest volume.")
