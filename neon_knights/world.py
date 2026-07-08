from __future__ import annotations

from .models import Ancestry, Augment, Enemy, Exit, Faction, Gear, NPC, Room


ANCESTRIES: dict[str, Ancestry] = {
    "vampire": Ancestry(
        "vampire",
        "Vampire",
        "An immortal predator learning to survive in a city of cameras and synthetic blood.",
        "Bloodsense: scan living rooms for heat, fear, and debt.",
    ),
    "werewolf": Ancestry(
        "werewolf",
        "Werewolf",
        "A moon-touched shapeshifter balancing rage, pack duty, and rent.",
        "Scentline: track recent movement and hidden biological traces.",
    ),
    "witch": Ancestry(
        "witch",
        "Witch",
        "A street occultist who writes hexes into firmware and subway dust.",
        "Hexcraft: spot improvised wards, curses, and ritual weak points.",
    ),
    "wizard": Ancestry(
        "wizard",
        "Wizard",
        "A formal spell engineer licensed to bend reality with dangerous precision.",
        "Protocol Sight: read structured magic and legal spellwork.",
    ),
    "demon": Ancestry(
        "demon",
        "Demon",
        "An infernal exile or contract-born citizen hiding old fire under new neon.",
        "Hellmark: sense desire, oath heat, infernal debt, and places where reality has been bargained thin.",
    ),
    "cyborg": Ancestry(
        "cyborg",
        "Cyborg",
        "A person remade with chrome, debt, scar tissue, and refusal.",
        "Systems Check: diagnose machines, augments, and damaged infrastructure.",
    ),
    "ai": Ancestry(
        "ai",
        "Awakened AI",
        "A self-authored intelligence walking the city through rented bodies and public terminals.",
        "Ghost Ping: sense networks, forks, machine spirits, and hostile code.",
    ),
    "human": Ancestry(
        "human",
        "Human Adept",
        "A mortal specialist with no ancient curse or factory warranty, which makes you underestimated.",
        "Edge: gain cleaner reads on social pressure and street opportunities.",
    ),
}


FACTIONS: dict[str, Faction] = {
    "blood-court": Faction(
        "blood-court",
        "Blood Court",
        "Every drop remembers.",
        "Vampire houses, blood-bank nobles, contract priests, and immortal fixers.",
    ),
    "pack-union": Faction(
        "pack-union",
        "Pack Union",
        "No body gets hunted alone.",
        "Werewolf crews, clinic workers, mechanics, and mutual-defense cells.",
    ),
    "hex-grid": Faction(
        "hex-grid",
        "Hex Grid",
        "Patch the curse. Curse the patch.",
        "Witches, rogue coders, charm dealers, and ritual street medics.",
    ),
    "chrome-synod": Faction(
        "chrome-synod",
        "Chrome Synod",
        "The body is a temple under renovation.",
        "Cyborg surgeons, body artists, hardware priests, and escaped military techs.",
    ),
    "synthetic-choir": Faction(
        "synthetic-choir",
        "Synthetic Choir",
        "A soul is a song with backups.",
        "Advanced AI citizens, machine mystics, memory lawyers, and distributed prophets.",
    ),
    "infernal-compact": Faction(
        "infernal-compact",
        "Infernal Compact",
        "Every deal leaves a door.",
        "Demon advocates, contract-breakers, temptation brokers, and exiled hell-nobility.",
    ),
}


AUGMENTS: dict[str, Augment] = {
    "bionic-eyes": Augment(
        "bionic-eyes",
        "Bionic Eyes",
        "eyes",
        500,
        8,
        "Thermal, astral, and low-light overlays reveal hidden room details.",
    ),
    "hydraulic-legs": Augment(
        "hydraulic-legs",
        "Hydraulic Legs",
        "legs",
        700,
        12,
        "Silent pistons and tendon motors unlock vertical movement routes.",
    ),
    "neural-spellware": Augment(
        "neural-spellware",
        "Neural Spellware",
        "nervous system",
        650,
        10,
        "A gray-market casting coprocessor for witches, wizards, and reckless everyone else.",
    ),
    "moon-silver-bones": Augment(
        "moon-silver-bones",
        "Moon-Silver Bones",
        "skeleton",
        800,
        16,
        "Reinforced bones tuned against shapeshifter trauma and occult impact.",
    ),
    "synth-heart": Augment(
        "synth-heart",
        "Synth Heart",
        "core",
        750,
        15,
        "A tireless pump that keeps blood, coolant, or ritual ichor moving.",
    ),
}


GEAR: dict[str, Gear] = {
    "street-knife": Gear(
        "street-knife",
        "Street Knife",
        "weapon",
        0,
        4,
        0,
        "A cheap ceramic blade, legal in three districts and useful in all of them.",
    ),
    "patchwork-coat": Gear(
        "patchwork-coat",
        "Patchwork Coat",
        "body",
        0,
        0,
        1,
        "A stitched coat lined with charm tags, mylar, and stubbornness.",
    ),
    "neon-dagger": Gear(
        "neon-dagger",
        "Neon Dagger",
        "weapon",
        120,
        8,
        0,
        "A mono-edge dagger with a sign-tube glow along the spine.",
    ),
    "shock-gauntlet": Gear(
        "shock-gauntlet",
        "Shock Gauntlet",
        "weapon",
        220,
        10,
        0,
        "A knuckle rig that hits like an angry transformer.",
    ),
    "hex-thread-jacket": Gear(
        "hex-thread-jacket",
        "Hex-Thread Jacket",
        "body",
        180,
        0,
        3,
        "A black street jacket sewn with warded conductive thread.",
    ),
    "rosary-fuse": Gear(
        "rosary-fuse",
        "Rosary Fuse",
        "charm",
        95,
        1,
        1,
        "A pocket charm made from glass beads, burned copper, and a tiny breaker switch.",
    ),
}


ENEMIES: dict[str, Enemy] = {
    "training-drone": Enemy(
        "training-drone",
        "Training Drone",
        6,
        2,
        40,
        "A battered tutorial drone with warning sigils taped over old police decals.",
    ),
    "market-ghoul": Enemy(
        "market-ghoul",
        "Market Ghoul",
        10,
        3,
        80,
        "A hungry data-ghoul sniffing for unattended wallets and warm memories.",
    ),
}


def build_rooms() -> dict[str, Room]:
    vexa = NPC(
        "vexa-13",
        "Vexa-13",
        "A chrome-faced AI advocate projects through a cracked station kiosk.",
        "Vexa-13 says, 'Citizenship is not granted. It is debugged in public.'",
    )
    mother_circuit = NPC(
        "mother-circuit",
        "Mother Circuit",
        "A witch with fiber-optic braids sells luck in disposable phones.",
        "Mother Circuit says, 'Never trust a clean spell. Clean means nobody survived testing it.'",
    )
    brickfang = NPC(
        "brickfang",
        "Brickfang",
        "A werewolf mechanic with silver tattoos and oil on both hands.",
        "Brickfang says, 'Chrome is fine. Chains are the problem. Know who owns your upgrades.'",
    )
    count_zero = NPC(
        "count-zero",
        "Count Zero",
        "A vampire courier in mirrored glasses inventories debt like ammunition.",
        "Count Zero says, 'Blood is just memory with a pulse.'",
    )
    archivist = NPC(
        "sable-archivist",
        "Sable Archivist",
        "A wizard in a polymer robe indexes spells by lawsuit, casualty, and moon phase.",
        "The Sable Archivist says, 'Improvisation is admirable after the containment circle is paid for.'",
    )

    return {
        "redline-station": Room(
            "redline-station",
            "Redline Station",
            "Maglev brakes scream under cathedral glass. Vampires avoid the sunrise ads, "
            "werewolves watch the exits, and vending machines whisper prayers in machine code.",
            exits=(
                Exit("north", "neon-bazaar", "A stairwell climbs into the market glow."),
                Exit("east", "synth-court", "A glass tunnel hums with arbitration engines."),
                Exit("west", "undercity-kennels", "Service stairs descend into Pack Union territory."),
                Exit(
                    "up",
                    "rooftop-garden",
                    "A broken maintenance shaft leads toward rain and open sky.",
                    required_augment="hydraulic-legs",
                ),
            ),
            npcs=(vexa,),
            enemies=("training-drone",),
            scan_text="The station grid shows old blood under platform three and a Choir relay in kiosk 7.",
            ascii_art=r"""
        ||        ||        ||
     ___||___  ___||___  ___||___
    |  RED  ||| LINE ||| STATION |
    |_______|||______|||_________|
       //         ||         \\
      //      .---||---.      \\
              |  R  |  |
              '-----'--'
""",
        ),
        "neon-bazaar": Room(
            "neon-bazaar",
            "Neon Bazaar",
            "Relic vendors and cyber-docs share stalls beneath animated prayer flags. "
            "A jar of vampire ash sits beside a rack of military-grade knee actuators.",
            exits=(
                Exit("south", "redline-station", "Return to the transit concourse."),
                Exit("north", "moonworks-clinic", "A blue-white clinic sign pulses above a side alley."),
                Exit("east", "hexspire-library", "A lane of spell-tagged shutters leads to the archive."),
                Exit("west", "blood-cathedral", "A red-lit arcade descends into velvet quiet."),
            ),
            npcs=(mother_circuit,),
            augments_for_sale=("bionic-eyes", "neural-spellware"),
            gear_for_sale=("neon-dagger", "hex-thread-jacket", "rosary-fuse"),
            enemies=("market-ghoul",),
            scan_text="Your scan catches curse graffiti, counterfeit relic IDs, and a camera that blinks like an eye.",
            ascii_art=r"""
    .---.    .---.    .---.    .---.
   /_NE_\   /_ON_\   /_BA_\   /_ZA_\
   |   |    |   |    |   |    |   |
   | $ |____| # |____| @ |____| ? |
   |___|    |___|    |___|    |___|
       relics  chrome  charms  teeth
""",
        ),
        "moonworks-clinic": Room(
            "moonworks-clinic",
            "Moonworks Clinic",
            "A werewolf-run clinic bolts cybernetics beside lunar trauma wards. "
            "Every consent form is written in plain language and claw-proof plastic.",
            exits=(
                Exit("south", "neon-bazaar", "Return to the bazaar."),
                Exit("down", "undercity-kennels", "A freight lift drops into the union garages."),
            ),
            npcs=(brickfang,),
            augments_for_sale=("hydraulic-legs", "moon-silver-bones", "synth-heart"),
            gear_for_sale=("shock-gauntlet", "hex-thread-jacket"),
            scan_text="The clinic network is clean, loud, and heavily defended by people who hate predators.",
            ascii_art=r"""
          _______________
     ____/ MOONWORKS RX \____
    /   _  _  _  _  _  _    \
   |   ( )( )( )( )( )( )    |
   |    chrome | bone | oath |
    \_______________________/
""",
        ),
        "blood-cathedral": Room(
            "blood-cathedral",
            "Blood Cathedral",
            "Smart glass saints bleed red light over black pews. "
            "Immortal patrons negotiate blood contracts in voices too soft for microphones.",
            exits=(
                Exit("east", "neon-bazaar", "Return to market noise."),
                Exit("down", "data-chapel", "A sealed stairway descends through humming server racks."),
            ),
            npcs=(count_zero,),
            scan_text="Heat signatures gather behind confession booths. The donation vault has teeth.",
            ascii_art=r"""
          /\        /\        /\
         /  \  /\  /  \  /\  /  \
        /____\/__\/____\/__\/____\
        |   BLOOD CATHEDRAL     |
        |  []  []  ||  []  []   |
        |_______.--||--.________|
""",
        ),
        "hexspire-library": Room(
            "hexspire-library",
            "Hexspire Library",
            "Old grimoires and quantum tablets orbit the same angry librarian. "
            "Witch tags crawl across wizard indexes, correcting the footnotes in real time.",
            exits=(
                Exit("west", "neon-bazaar", "Return to the bazaar."),
                Exit("south", "synth-court", "Follow a corridor of contract sigils and server lights."),
            ),
            npcs=(archivist,),
            scan_text="The shelves rearrange around forbidden searches. Somebody recently requested your name.",
            ascii_art=r"""
       __________________________
      / HEXSPIRE STACKS  /|     /|
     /__________________/ |____/ |
     |  [sigil] [code] |  |    | |
     |  [curse] [case] |  |    | /
     |_________________|__|____|/
""",
        ),
        "synth-court": Room(
            "synth-court",
            "Synth Court",
            "An open-air court of glass terminals hosts AI citizens, legal ghosts, and human witnesses. "
            "Every sentence spoken here is notarized by three disagreeing machines.",
            exits=(
                Exit("west", "redline-station", "Return to Redline Station."),
                Exit("north", "hexspire-library", "Take the sigil corridor to the library."),
                Exit("down", "data-chapel", "A logic-locked lift descends to the chapel servers."),
            ),
            npcs=(vexa,),
            scan_text="Public case law scrolls overhead: personhood, fork rights, memory crimes, unpaid cloud rent.",
            ascii_art=r"""
      ______________________________
     / SYNTH COURT // PUBLIC LOGIC /
    /______________________________/
        |  0101  |  OATH  |  1010
        |________|________|_______
""",
        ),
        "undercity-kennels": Room(
            "undercity-kennels",
            "Undercity Kennels",
            "Below the maglev, Pack Union garages shake with engines, drums, and argument. "
            "This is not a kennel unless you are trying to start a fight.",
            exits=(
                Exit("east", "redline-station", "Climb back to the station."),
                Exit("up", "moonworks-clinic", "Ride the freight lift to the clinic."),
            ),
            npcs=(brickfang,),
            scan_text="Fresh claw marks, old police drones, and a hidden medical cache map the room's politics.",
            ascii_art=r"""
      ==============================
       UNDERCITY PACK UNION GARAGE
      ==============================
       ||  engines  ||  drums  ||
       ||__claws____||__oaths__||
""",
        ),
        "data-chapel": Room(
            "data-chapel",
            "Data Chapel",
            "Server towers rise like organ pipes. Electric candles blink beside bowls of blood, oil, and rainwater.",
            exits=(
                Exit("up", "blood-cathedral", "Climb toward the Blood Cathedral."),
                Exit("north", "synth-court", "Take the logic lift to Synth Court."),
            ),
            npcs=(vexa, mother_circuit),
            scan_text="A distributed hymn pings through the racks. Some replies arrive before the question.",
            ascii_art=r"""
        | | | | | | | | | | |
        | DATA CHAPEL SERVERS |
        | | | | | | | | | | |
          candles: oil / blood / rain
""",
        ),
        "rooftop-garden": Room(
            "rooftop-garden",
            "Rooftop Garden",
            "Rain beads on solar leaves and illegal moonflowers. "
            "The city sprawls below, all hunger, signal, spelllight, and sirens.",
            exits=(
                Exit("down", "redline-station", "Drop through the maintenance shaft to the station."),
            ),
            scan_text="The skyline exposes faction borders: red towers, green clinic signs, silver court lights.",
            ascii_art=r"""
          .       .        .
       ___|___ ___|___  ___|___
      / moonflowers and wet solar leaves \
     /____________________________________\
          skyline: hunger / signal / spell
""",
        ),
    }
