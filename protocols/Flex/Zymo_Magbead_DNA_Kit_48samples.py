def get_values(*names):
    import json
    _all_values = json.loads("""{"trash_chute":false,"USE_GRIPPER":true,"dry_run":false,"mount":"right","temp_mod":true,"res_type":"nest_12_reservoir_15ml","heater_shaker":true,"num_samples":48,"wash1_vol":500,"wash2_vol":900,"wash3_vol":900,"sample_vol":200,"bind_vol":600,"bind2_vol":500,"elution_vol":50,"protocol_filename":"Zymo_Magbead_DNA_TestRun_24samples"}""")
    return [_all_values[n] for n in names]

from opentrons.types import Point
import json
import math
from opentrons import types
import numpy as np

metadata = {
    'protocolName': 'Zymo Magbead DNA Extraction 48 Samples V1.3',
    'author': 'OpentronsAI',
    'description': 'DNA extraction protocol using magnetic beads',
    'source': 'OpentronsAI'
}

requirements = {
    "robotType": "Flex",
    "apiLevel": "2.22"
}

whichwash   = 1
sample_max  = 48
tip1k       = 0
tip200      = 0
drop_count  = 0

def run(ctx):
    """
    DNA Extraction of 48 Samples
    """
    trash_chute    = False
    USE_GRIPPER    = True
    dry_run        = False
    mount          = 'right'
    res_type       = "nest_12_reservoir_15ml"
    temp_mod       = True
    heater_shaker  = True

    num_samples    = 48
    wash1_vol      = 500
    wash2_vol      = 900
    wash3_vol      = 900
    sample_vol     = 200
    bind_vol       = 600
    bind2_vol      = 500
    elution_vol    = 50

    try:
        [res_type,temp_mod,trash_chute,USE_GRIPPER, dry_run,mount,num_samples,heater_shaker,wash1_vol,wash2_vol,wash3_vol,sample_vol,bind_vol,bind2_vol,elution_vol] = get_values(
        'res_type','temp_mod','trash_chute','USE_GRIPPER','dry_run','mount','num_samples','heater_shaker','wash1_vol','wash2_vol','wash3_vol','sample_vol','bind_vol','bind2_vol','elution_vol')
    except (NameError):
        pass

    # Protocol Parameters
    deepwell_type = "nest_96_wellplate_2ml_deep"
    
    if not dry_run:
        settling_time = 2
        settling_time_binding = 5
        settling_time_wash = 1
    else:
        settling_time = 0.25
        settling_time_binding = 0.25
        settling_time_wash = 0.25

    bead_vol = 20
    starting_vol = sample_vol 
    binding_buffer_vol = bind_vol + bead_vol
    
    # Load trash - keeping original position D3
    if trash_chute:
        trash = ctx.load_waste_chute()
    else:
        trash = ctx.load_trash_bin('D3')

    # Load modules - keeping original positions
    if heater_shaker:
        h_s = ctx.load_module('heaterShakerModuleV1','D1')
        h_s_adapter = h_s.load_adapter('opentrons_96_deep_well_adapter')
        sample_plate = h_s_adapter.load_labware(deepwell_type,'Samples')
        h_s.close_labware_latch()
    else:
        sample_plate = ctx.load_labware(deepwell_type,'D1','Samples')
    
    if temp_mod:
        temp = ctx.load_module('temperature module gen2','A3')
        temp_block = temp.load_adapter('opentrons_96_well_aluminum_block')
        elutionplate = temp_block.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt','Elution Plate')
    else:
        elutionplate = ctx.load_labware('opentrons_96_wellplate_200ul_pcr_full_skirt','A3','Elution Plate')

    # Load other modules and labware - keeping original positions
    magblock = ctx.load_module('magneticBlockV1','C1')
    waste = ctx.load_labware('nest_1_reservoir_195ml', 'C3','Liquid Waste').wells()[0].top()
    res1 = ctx.load_labware(res_type, 'D2', 'reagent reservoir 1')
    res2 = ctx.load_labware(res_type, 'C2', 'reagent reservoir 2')
    num_cols = math.ceil(num_samples/8)
    
    # Load tips
    tips1000 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', 'A2','Tips 4')
    tips1001 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', 'B2','Tips 2')
    tips1002 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', 'B3','Tips 1')
    tips1003 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', 'A1','Tips 5')
    tips1004 = ctx.load_labware('opentrons_flex_96_tiprack_1000ul', 'B1','Tips 3')
    tips = [*tips1000.wells(),*tips1001.wells(),*tips1002.wells(),*tips1003.wells(),*tips1004.wells()]
 
    # Load instruments
    m1000 = ctx.load_instrument('flex_8channel_1000', mount, tip_racks=[tips1000, tips1001, tips1002, tips1003, tips1004])

    # Define reagent locations
    binding_buffer = res1.wells()[0:3]
    bind2_res = res1.wells()[4:6]
    wash1 = res1.wells()[7:9]
    elution_solution = res1.wells()[-1]
    wash2 = res2.wells()[:6]
    wash3 = res2.wells()[6:]

    samples_m = sample_plate.rows()[0][:num_cols]
    elution_samples_m = elutionplate.rows()[0][:num_cols]
    samps = sample_plate.wells()[:(8*num_cols)]
    elution_samps = elutionplate.wells()[:(8*num_cols)]

    colors = ['#008000','#008000','#00008B','#A52A2A','#00FFFF','#00FFFF','#800080',
    '#ADD8E6','#FF0000','#FFFF00','#FF00FF','#7FFFD4',
    '#FFC0CB','#FFA500','#00FF00','#C0C0C0']

    locations = [binding_buffer,binding_buffer,bind2_res,wash1,wash2,wash3,elution_solution]
    vols = [bead_vol,bind_vol,bind2_vol,wash1_vol,wash2_vol,wash3_vol,elution_vol]
    liquids = ['MagBinding Beads','MagBinding Buffer','MagBinding Buffer (Wash)','MagWash 1','MagWash 2 (1)','MagWash 2 (2)','DNase/RNase Free Water']

    # Define liquids
    samples = ctx.define_liquid(name='Samples',description='Samples',display_color='#C0C0C0')
    
    for i in samps:
        i.load_liquid(liquid=samples,volume=0)

    delete = len(colors)-len(liquids)
    if delete>=1:
        for i in range(delete):
            colors.pop(-1)

    def liquids_(liq,location,color,vol):
        sampnum = 8*(math.ceil(num_samples/8))
        
        if liq == "MagBinding Beads":
            extra_samples = math.ceil(1500/bind_vol)
        else:
            extra_samples = math.ceil(1500/vol)
        
        if isinstance(location,list):
            limit = sample_max/len(location)
            iterations = math.ceil(sampnum/limit)
            left = sampnum - limit
            while left>limit:
                left = left - limit
            if left > 0:
                last_iteration_samp_num = left
            elif left < 0:
                last_iteration_samp_num = sampnum
            else:
                last_iteration_samp_num = limit

            samples_per_well = []
            for i in range(iterations):
                if i == (iterations-1):
                    samples_per_well.append(last_iteration_samp_num)
                else:
                    samples_per_well.append(limit)

            liq = ctx.define_liquid(name=str(liq),description=str(liq),display_color=color)
            for sample, well in zip(samples_per_well,location[:len(samples_per_well)]):
                v = vol*(sample+extra_samples)
                well.load_liquid(liquid=liq,volume=v)
        else:
            v = vol*(sampnum+extra_samples)
            liq = ctx.define_liquid(name=str(liq),description=str(liq),display_color=color)
            location.load_liquid(liquid=liq,volume=v)

    for x,(ll,l,c,v) in enumerate(zip(liquids,locations,colors,vols)):
        liquids_(ll,l,c,v)

    m1000.flow_rate.aspirate = 180
    m1000.flow_rate.dispense = 300
    m1000.flow_rate.blow_out = 180

    def tiptrack(pip, tipbox):
        global tip1k
        global drop_count
        if tipbox == tips:
            m1000.pick_up_tip(tipbox[int(tip1k)])
            tip1k = tip1k + 8

        drop_count = drop_count + 8
        if drop_count >= 150:
            drop_count = 0
            ctx.pause("Please empty the waste bin of all the tips before continuing.")

    def blink():
        for i in range(3):
            ctx.set_rail_lights(True)
            ctx.delay(minutes=0.01666667)
            ctx.set_rail_lights(False)
            ctx.delay(minutes=0.01666667)

    def remove_supernatant(vol):
        ctx.comment("-----Removing Supernatant-----")
        m1000.flow_rate.aspirate = 30
        num_trans = math.ceil(vol/980)
        vol_per_trans = vol/num_trans

        def _waste_track(vol):
            global waste_vol 
            waste_vol = waste_vol + (vol*8)
            if waste_vol >= 185000:
                m1000.home()
                blink()
                ctx.pause('Please empty liquid waste before resuming.')
                waste_vol = 0
        
        for i, m in enumerate(samples_m):
            tiptrack(m1000,tips)
            loc = m.bottom(3)
            loc2 = m.bottom(1)
            for _ in range(num_trans):
                if m1000.current_volume > 0:
                    m1000.dispense(m1000.current_volume, m.top())
                m1000.move_to(m.center())
                m1000.transfer(vol_per_trans, loc, waste, new_tip='never',air_gap=20)
                m1000.blow_out(waste)
                m1000.air_gap(20)
		
                m1000.move_to(m.center())
                m1000.transfer(200, loc2, waste, new_tip='never',air_gap=20)
                m1000.blow_out(waste)
                m1000.air_gap(20)
            m1000.drop_tip()
        m1000.flow_rate.aspirate = 180

        # Transfer from Magdeck plate to H-S
        if heater_shaker:
            h_s.open_labware_latch()
        ctx.move_labware(
            sample_plate,
            h_s_adapter if heater_shaker else 'D1',
            use_gripper=USE_GRIPPER,
            drop_offset={"x": 0, "y": 0, "z": -1.5}
        )
        if heater_shaker:
            h_s.close_labware_latch()

    def bead_mixing(well, pip, mvol, reps=8):
        center = well.top().move(types.Point(x=0,y=0,z=5))
        aspbot = well.bottom().move(types.Point(x=0,y=2,z=1))
        asptop = well.bottom().move(types.Point(x=0,y=-2,z=2))
        disbot = well.bottom().move(types.Point(x=0,y=2,z=3))
        distop = well.top().move(types.Point(x=0,y=1,z=-5))

        if mvol > 1000:
            mvol = 1000

        vol = mvol * .8

        pip.flow_rate.aspirate = 500
        pip.flow_rate.dispense = 500

        pip.move_to(center)
        for _ in range(reps):
            pip.aspirate(vol,aspbot)
            pip.dispense(vol,distop)
            pip.aspirate(vol,asptop)
            pip.dispense(vol,disbot)
            if _ == reps-1:
                pip.flow_rate.aspirate = 150
                pip.flow_rate.dispense = 100
                pip.aspirate(vol,aspbot)
                pip.dispense(vol,distop)

        pip.flow_rate.aspirate = 300
        pip.flow_rate.dispense = 300

    def mixing(well, pip, mvol, reps=8):
        center = well.top(5)
        asp = well.bottom(1)
        disp = well.top(-8)

        if mvol > 1000:
            mvol = 1000

        vol = mvol * .8

        pip.flow_rate.aspirate = 500
        pip.flow_rate.dispense = 500

        pip.move_to(center)
        for _ in range(reps):
            pip.aspirate(vol,asp)
            pip.dispense(vol,disp)
            pip.aspirate(vol,asp)
            pip.dispense(vol,disp)
            if _ == reps-1:
                pip.flow_rate.aspirate = 150
                pip.flow_rate.dispense = 100
                pip.aspirate(vol,asp)
                pip.dispense(vol,disp)

        pip.flow_rate.aspirate = 300
        pip.flow_rate.dispense = 300

    def bind(vol1,vol2):
        ctx.comment('-----Beginning Binding Steps-----')
        for i, well in enumerate(samples_m):
            tiptrack(m1000,tips)
            num_trans = math.ceil(vol1/980)
            vol_per_trans = vol1/num_trans
            source = binding_buffer[i//2]
            if i == 0:
                reps=5
            else:
                reps=2
            bead_mixing(source,m1000,vol_per_trans,reps=reps if not dry_run else 1)
            
            for t in range(num_trans):
                if m1000.current_volume > 0:
                    m1000.dispense(m1000.current_volume, source.top())
                m1000.transfer(vol_per_trans, source, well.top(), air_gap=20,new_tip='never')
                m1000.air_gap(20)
            
            mixing(well,m1000,vol_per_trans,reps=8 if not dry_run else 1)
            m1000.blow_out()
            m1000.air_gap(20)
            m1000.drop_tip()
                       
        if heater_shaker:
            h_s.set_and_wait_for_shake_speed(1800)
            ctx.delay(minutes=10 if not dry_run else 0.25, msg='Shake at 1800 rpm for 10 minutes.')
            h_s.deactivate_shaker()
        else:
            if not dry_run:
                ctx.pause(msg="Place on shaker at 1800 rpm for 10 minutes")

        # Transfer from H-S plate to Magdeck plate
        if heater_shaker:
            h_s.open_labware_latch()
        ctx.move_labware(
            sample_plate,
            magblock,
            use_gripper=USE_GRIPPER,
            drop_offset={"x": 0, "y": 0, "z": -1}
        )
        if heater_shaker:
            h_s.close_labware_latch()

        for bindi in np.arange(settling_time_binding+1,0,-0.5):
            ctx.delay(minutes=0.5, msg='There are ' + str(bindi) + ' minutes left in the incubation.')

        # Remove initial supernatant
        remove_supernatant(vol1+starting_vol)

        ctx.comment('-----Beginning Bind #2 Steps-----')
        tiptrack(m1000,tips)
        for i, well in enumerate(samples_m):
            num_trans = math.ceil(vol2/980)
            vol_per_trans = vol2/num_trans
            source = bind2_res[i//3]
            if i == 0 or i == 3:
                height = 10
            else:
                height = 1
            
            for t in range(num_trans):
                if m1000.current_volume > 0:
                    m1000.dispense(m1000.current_volume, source.top())
                m1000.transfer(vol_per_trans, source.bottom(height), well.top(), air_gap=20,new_tip='never')
                m1000.air_gap(20)

        for i in range(num_cols):
            if i != 0:
                tiptrack(m1000,tips)
            mixing(samples_m[i],m1000,vol_per_trans,reps=8 if not dry_run else 1)
            m1000.drop_tip()

        if heater_shaker:
            h_s.set_and_wait_for_shake_speed(1800)
            ctx.delay(minutes=1 if not dry_run else 0.25, msg='Shake at 1800 rpm for 1 minutes.')
            h_s.deactivate_shaker()
        else:
            if not dry_run:
                ctx.pause("Place on shaker at 1800 rpm for 1 minute.")

        # Transfer from H-S plate to Magdeck plate
        if heater_shaker:
            h_s.open_labware_latch()
        ctx.move_labware(
            sample_plate,
            magblock,
            use_gripper=USE_GRIPPER,
            drop_offset={"x": 0, "y": 0, "z": -1}
        )
        if heater_shaker:
            h_s.close_labware_latch()

        for bindi in np.arange(settling_time_wash+1,0,-0.5):
            ctx.delay(minutes=0.5, msg='There are ' + str(bindi) + ' minutes left in the incubation.')

        # Remove initial supernatant
        remove_supernatant(vol2+25)

    def wash(vol, source):
        global whichwash

        if source == wash1:
            whichwash = 1
            const = 6//len(source)
        if source == wash2:
            whichwash = 2
            const = 6//len(source)
            height = 1
        if source == wash3:
            whichwash = 3
            const = 6//len(source)
            height = 1

        ctx.comment("-----Wash #" + str(whichwash) + " is starting now------")

        num_trans = math.ceil(vol/980)
        vol_per_trans = vol/num_trans
        
        tiptrack(m1000,tips)
        for i, m in enumerate(samples_m):
            if source == wash1:
                if i == 0 or i == 3:
                    height = 10
                else:
                    height = 1
            src = source[i//const]
            for n in range(num_trans):
                if m1000.current_volume > 0:
                    m1000.dispense(m1000.current_volume, src.top())
                m1000.transfer(vol_per_trans, src.bottom(height), m.top(), air_gap=20,new_tip='never')
        m1000.drop_tip() 

        if heater_shaker:
            h_s.set_and_wait_for_shake_speed(1800)
            ctx.delay(minutes=2 if not dry_run else 0.25)
            h_s.deactivate_shaker()
        else:
            if not dry_run:
                ctx.pause(msg="Shaker for 2 minutes at 1800 rpm")

        if heater_shaker:
            h_s.open_labware_latch()
        ctx.move_labware(
            sample_plate,
            magblock,
            use_gripper=USE_GRIPPER,
            drop_offset={"x": 0, "y": 0, "z": -1}
        )

        if heater_shaker:
            h_s.close_labware_latch()

        for washi in np.arange(settling_time_wash,0,-0.5):
            ctx.delay(minutes=0.5, msg='There are ' + str(washi) + ' minutes left in wash ' + str(whichwash) + ' incubation.')

        remove_supernatant(vol)

    def elute(vol):
        tiptrack(m1000,tips)
        for i, m in enumerate(samples_m):
            m1000.aspirate(vol, elution_solution)
            m1000.air_gap(5)
            m1000.dispense(m1000.current_volume, m.top(-3))
        m1000.drop_tip()

        if heater_shaker:
            h_s.set_and_wait_for_shake_speed(1800)
            ctx.delay(minutes=5 if not dry_run else 0.25,msg='Shake on H-S for 5 minutes at 1800 rpm.')
            h_s.deactivate_shaker()
        else:
            if not dry_run:
                ctx.pause(msg="Place on a shaker at 1800 rpm for 5 minutes.")

        # Transfer back to magnet
        if heater_shaker:
            h_s.open_labware_latch()
        ctx.move_labware(
            sample_plate,
            magblock,
            use_gripper=USE_GRIPPER,
            drop_offset={"x": 0, "y": 0, "z": -1}
        )
        if heater_shaker:
            h_s.close_labware_latch()

        for elutei in np.arange(settling_time,0,-0.5):
            ctx.delay(minutes=0.5, msg='Incubating on MagDeck for ' + str(elutei) + ' more minutes.') 

        for i, (m, e) in enumerate(zip(samples_m, elution_samples_m)):
            tiptrack(m1000,tips)
            m1000.flow_rate.dispense = 100
            m1000.flow_rate.aspirate = 25
            m1000.transfer(vol, m.bottom(0.3), e.bottom(5), air_gap=5, new_tip='never')
            m1000.blow_out(e.top(-2))
            m1000.air_gap(5)
            m1000.drop_tip()

        m1000.flow_rate.aspirate = 150

    # Protocol execution
    bind(binding_buffer_vol,bind2_vol)
    wash(wash1_vol, wash1)
    if not dry_run:
        wash(wash2_vol, wash2)
        wash(wash3_vol, wash3)
        drybeads = 9
        if heater_shaker:
            h_s.set_and_wait_for_temperature(55)
    else:
        drybeads = 0.5
    for beaddry in np.arange(drybeads,0,-0.5):
        ctx.delay(minutes=0.5, msg='There are ' + str(beaddry) + ' minutes left in the drying step.')
    elute(elution_vol)
    if heater_shaker:
        h_s.deactivate_heater()
