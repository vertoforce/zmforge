"""Names the game fixes, gathered in one table each.

Everything in this module is a **fixed name** in the sense of spec section
0.2: an asset path, a classname, a key, a key's required value, or a script
module.  They are spelled here exactly once so that no other module has to
hold a literal, and so a reader can audit the whole fixed set in one place.

The *variables* are named for their role, not for the string they hold (spec
section 0.3, rule 4): ``ZONE_MARKER_TAG`` holds ``script_noteworthy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..spatial import Facing

__all__ = [
    "PerkKind",
    "PERKS",
    "perk_named",
    "WALL_WEAPONS",
    "CHALKLESS_WALL_WEAPONS",
    "WALL_WEAPON_WEAPONS",
    "wall_weapon_weapon",
    "DOOR_MODELS",
    "DEFAULT_DOOR_MODEL",
    "DOOR_LEAF_SIZE",
    "BARRICADE_PREFAB",
    "BARRICADE_PREFAB_HIDE_DEBRIS",
    "MYSTERY_BOX_PREFAB",
    "POWER_SWITCH_PREFAB",
    "PROP_PALETTE",
    "STOCK_PROPS",
    "prefab_yaw",
    "prefab_front_zero",
    "PREFAB_FRONT_ZERO_BY_MODEL",
    "UNMEASURED_PREFAB_FRONT_ZERO",
    "PERK_FRONT_ZERO",
    "PACK_A_PUNCH_FRONT_ZERO",
    "GOBBLEGUM_FRONT_ZERO",
    "MYSTERY_BOX_FRONT_ZERO",
    "POWER_SWITCH_FRONT_ZERO",
    "WALL_WEAPON_FRONT_ZERO",
    "wall_weapon_yaw",
    "BARRICADE_EXTERIOR_ZERO",
    "LEVEL_WEAPONS",
    "BOX_WEAPONS",
    "MAGIC_BOX_BARRIER",
    "SPAWN_GAMETYPES",
    "START_LOCATION",
    "spawn_string_tokens",
    "MODEL_COMPANIONS",
    "companions_of",
    "ROUTE_WORDS",
    "ROUTE_MODELS",
    "ROUTE_TOP",
    "is_route_model",
    "route_top",
    "companion_origins",
]

_CORE_PREFABS = "_prefabs/zm/zm_core"


# --------------------------------------------------------------------------
# Orientation
# --------------------------------------------------------------------------
# Two numbers decide where a prefab ends up pointing: which way the asset
# faces when its yaw is 0, and which way the yaw turns it.  Both are measured
# here, and they were measured the same way for every family.
#
# The turn is **counter-clockwise**.  ``cod2map64`` was caught doing it on the
# compiled ``zm_mymap.d3dbsp`` (see :func:`wall_weapon_yaw`), and the
# engine turns the entities we emit ourselves -- the magic-box zbarrier, the
# chest struct -- the same way.  So one formula covers the lot:
#
#     yaw = (heading - front_at_yaw_zero) mod 360
#
# The front-at-yaw-zero is per family, and the families disagree.  Each one
# below was read off its own stock prefab under
# ``map_source/_prefabs/zm/zm_core`` on the tools install, the way
# the wall-buy family was read.  Spec appendix B carries the
# same table and the evidence for each row.


def prefab_yaw(heading: Facing, zero_heading: Facing) -> float:
    """Yaw in degrees that turns ``zero_heading`` onto ``heading``.

    Counter-clockwise in plan view, which is what ``cod2map64`` and the engine
    both do.  ``zero_heading`` is the caller's family front-at-yaw-zero; there
    is no default, because the families disagree and a default is how the
    clockwise version of this function went unnoticed while it aimed ten of
    eleven wall buys into their own walls.
    """
    return (heading.world_yaw - zero_heading.world_yaw) % 360.0


#: The heading a stock ``spawnable_weapon_<slug>`` prefab's front points at
#: yaw 0, **measured** on the mod-tools install.  Every one of the
#: thirteen prefabs under ``map_source/_prefabs/zm/zm_core`` is built the same
#: way: the chalk patch mesh and the weapon's ``script_struct`` sit on the
#: plane ``y = 0`` and the mount brush sits *behind* them at ``y in [-8, -1]``.
#: So the prefab expects the wall surface at its own origin plane with the
#: wall body at negative Y and the room at positive Y: its front is +Y, north.
WALL_WEAPON_FRONT_ZERO = Facing.NORTH

#: The heading a stock perk prefab's front points at yaw 0, **measured**
#: on all nine ``vending_*_struct.map`` prefabs bar the
#: pack-a-punch.  Three independent marks inside those files agree, and all
#: three sit on -Y: the ``attack_spot`` structs form an arc in front of the
#: machine at ``y`` between -19 and -38 with ``x`` at 0 and +/-30; the
#: ``PRIMARY_SPOT`` lights that light the machine's face stand 80 to 87 units
#: out at ``y`` about -80 aimed back at it (``light_perk_doubletap_001`` is the
#: clearest); and ``vending_revive_struct.map``'s one shadowcaster brush sits
#: behind the machine at ``y in [11, 17]``.  So the front is -Y, south.
PERK_FRONT_ZERO = Facing.SOUTH

#: The pack-a-punch is **not** on the perk heading, **measured**.
#: ``vending_weapon_upgrade_spawnable.map`` is the one vending prefab whose
#: own entities are not authored at yaw 0: both the ``zbarrier_zmcore_packapunch``
#: and the ``perksacola`` struct carry ``"angles" "0 270 0"``, which turns the
#: family's -Y front onto -X.  Its lighting says the same thing without
#: assuming anything about the model: the spot light at ``(8.75, 4.75, 68)``
#: targets an ``info_null`` 71 units away at ``(-63, 4.8, 68)``, and the second
#: ``info_null`` is at ``x = -59`` as well.  Everything in front of this
#: machine is at -X, so its front is -X, west.
PACK_A_PUNCH_FRONT_ZERO = Facing.WEST

#: The heading the mystery box's front points at yaw 0, **measured**.
#: ``buyable_magic_box_start.map`` itself cannot say: it is a
#: plank on four cinder blocks with a clip over it, no trigger, no struct and
#: no model with a face, and it is symmetric about its own origin bar the
#: decorative yaw jitter on the blocks.  What has a front is the
#: ``zbarrier_zmcore_MagicBox`` we emit beside it, and the stock script places
#: its use prompt: ``_zm_magicbox.gsc:294`` puts the unitrigger at
#: ``origin + anglestoright(angles) * -22.5``, which is 22.5 units along +Y at
#: yaw 0.  ``anglestoright`` is pinned by the wall buys, whose front is already
#: measured: ``_zm_weapons.gsc:959`` pushes their unitrigger the same way, and
#: for those it has to land in the room at +Y.  So the box's front is +Y,
#: north -- the opposite of the perk heading.
#:
#: The two entities agree on more than the front.  Treyarch's own pairing in
#: ``_prefabs/zm/zm_giant/script/zm_giant_magicboxes.map`` puts the platform
#: prefab at the zbarrier's yaw plus 90 at all six chests, and that platform's
#: long axis is Y (its crate models sit at ``y = +36`` and ``y = -35``), so the
#: box's long axis at yaw 0 is X -- the same as this stand's plank, which runs
#: ``x in [-46, 48]`` by ``y in [-13, 12.5]``.  Emitting stand and box at one
#: yaw is right; the yaw is what was wrong.
MYSTERY_BOX_FRONT_ZERO = Facing.NORTH

#: The heading the power switch's front points at yaw 0, **measured**,
#: and the least ambiguous of the set, because ``power_switch.map``
#: carries its own ``trigger_use``.  That trigger brush spans ``y in [-24, -5]``
#: while the switch body's clip is ``y in [-8, 7]``, so the trigger stands
#: entirely off the -Y face.  The handle ``script_model`` is at ``y = -7`` and
#: the ``elec_switch_fx`` struct at ``y = -8.3``, both on that same face.  The
#: front is -Y, south.
POWER_SWITCH_FRONT_ZERO = Facing.SOUTH

#: The heading a barricade prefab's exterior points at yaw 0, **measured**
#: on ``barricade_reciever_wood.map``.  The zombie side of the
#: prefab is all at +Y: the ``exterior_goal`` struct at ``(0, 50, 16)``, the
#: ``node_pathnode`` at ``(0, 63, 16)`` and the ``zbarrier`` itself at
#: ``(0, 47, 31)``, with the window's traverse brush at ``y in [-2, 14]``.
#: The exterior points +Y, north (measured), and the turn applied to it is
#: the counter-clockwise one.
BARRICADE_EXTERIOR_ZERO = Facing.NORTH

# The riser paired with a barricade is not a prefab and has no family front:
# it is an AI spawn struct, and its angles are a plain world heading.  The
# stock file settles what that heading should be -- barricade_reciever_wood's
# own ``exterior_goal`` struct stands outside at ``(0, 50, 16)`` carrying
# ``"angles" "0 270 0"``, a world heading of south, pointing straight back at
# the barricade at the origin.  So a riser faces the opposite of the exterior
# heading, and *not* "the barricade prefab's yaw plus 180": those two rules
# agree on no heading at all.

#: The GobbleGum machine's front at yaw 0.  ``vending_bgb_struct.map`` holds
#: no trigger, no struct and no light -- just the zbarrier and one clip brush
#: -- and the machine's own logic is not in the shipped scripts, so this is
#: the weakest row in the table and the only one with no script or struct to
#: corroborate it.  What the clip does say: its body is symmetric,
#: ``x in [-16, 16]`` by ``y in [-16, 16]``, but its top is a ``clip_slick``
#: slope that runs from ``z = 64`` at ``y = -16`` up to ``z = 96`` at
#: ``y = +16``.  The low, sheds-you-forward side is -Y, the same front as the
#: other eight machines, and the tall side is the one that goes against a
#: wall.  Treat the -Y as **[measured from the clip, not from a trigger]**.
GOBBLEGUM_FRONT_ZERO = Facing.SOUTH

#: The front-at-yaw-zero for a stock prefab placed by path rather than through
#: one of the element types that knows its own family.  Only prefabs that have
#: actually been read on the install are in here; a path that is missing is
#: missing on purpose and :data:`UNMEASURED_PREFAB_FRONT_ZERO` covers it while
#: ``Z23`` says so.
PREFAB_FRONT_ZERO_BY_MODEL: dict[str, Facing] = {
    f"{_CORE_PREFABS}/power_switch.map": POWER_SWITCH_FRONT_ZERO,
    f"{_CORE_PREFABS}/buyable_magic_box_start.map": MYSTERY_BOX_FRONT_ZERO,
    f"{_CORE_PREFABS}/barricade_reciever_wood.map": BARRICADE_EXTERIOR_ZERO,
    f"{_CORE_PREFABS}/barricade_reciever_wood_hide_pieces.map": BARRICADE_EXTERIOR_ZERO,
    f"{_CORE_PREFABS}/vending_weapon_upgrade_spawnable.map": PACK_A_PUNCH_FRONT_ZERO,
    f"{_CORE_PREFABS}/vending_bgb_struct.map": GOBBLEGUM_FRONT_ZERO,
    **{
        f"{_CORE_PREFABS}/vending_{slug}.map": PERK_FRONT_ZERO
        for slug in (
            "juggernaut_struct",
            "sleight_struct",
            "revive_struct",
            "doubletap_struct",
            "deadshot_struct",
            "marathon_struct",
            "additionalprimaryweapon_struct",
        )
    },
}

#: What a prefab whose front nobody has read gets.  It is a guess, it is named
#: as one, and ``Z23`` warns on every prefab that lands on it.  South is the
#: majority of the measured table, not a measurement of the model in hand.
UNMEASURED_PREFAB_FRONT_ZERO = Facing.SOUTH


def prefab_front_zero(model: str) -> Facing | None:
    """The measured front-at-yaw-zero for a stock prefab path, or ``None``.

    ``None`` is the honest answer for any prefab nobody has opened, and the
    callers treat it as one: the emitter falls back to
    :data:`UNMEASURED_PREFAB_FRONT_ZERO` and ``Z23`` reports it.
    """
    return PREFAB_FRONT_ZERO_BY_MODEL.get(str(model).strip())


def wall_weapon_yaw(heading: Facing) -> float:
    """Yaw for a wall-buy prefab whose front should point ``heading``.

    Counter-clockwise, which is what the compiler actually does.  Measured
    from a wall buy in a test map: the ``misc_prefab`` entity
    sat at origin ``(-1264, -100, 8)`` with ``angles`` yaw 270, the weapon
    struct inside ``spawnable_weapon_pistol_burst.map`` sits at local
    ``(-3, 0, 55)``, and the compiled ``zm_mymap.d3dbsp`` carries
    that struct at world ``(-1264, -97, 63)``.  A counter-clockwise yaw of
    270 maps local ``(x, y)`` to ``(y, -x)`` and so ``(-3, 0)`` to
    ``(0, 3)``, which is the offset in the BSP; the clockwise reading would
    have put it at ``(0, -3)``.

    This is :func:`prefab_yaw` against :data:`WALL_WEAPON_FRONT_ZERO` and
    nothing else; it keeps its own name because the measurement above is what
    established the turn for every family.
    """
    return prefab_yaw(heading, WALL_WEAPON_FRONT_ZERO)


# --------------------------------------------------------------------------
# Perks and pack-a-punch
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PerkKind:
    """One vending machine: its slug, its prefab and the module it needs.

    ``module`` is the ``#using`` path the map's scripts must carry -- both
    of them, server and client, as Treyarch's own map does
    (``zm_giant.gsc:30-38`` against ``zm_giant.csc:21-28``) -- or the machine
    has no logic at all on the side that is missing it (spec section 4.7).
    ``None`` means the usermap framework already provides it.
    """

    slug: str
    prefab: str | None
    module: str | None
    aliases: tuple[str, ...] = ()
    #: Which way this machine's prefab faces at yaw 0.  It is per machine and
    #: not per family because the pack-a-punch is genuinely not on the perk
    #: heading: see :data:`PACK_A_PUNCH_FRONT_ZERO`.
    front_zero: Facing = PERK_FRONT_ZERO
    #: Set on the perks the install ships a *model* for but no prefab.  The
    #: pair is what ``_zm_perks.gsc`` reads off the struct; see
    #: :data:`STRUCT_ONLY_MACHINES` for the measurement.
    xmodel: str | None = None
    #: The ``specialty_`` string the game knows this perk by, as
    #: ``_zm_perks.gsh:31-43`` ``#define``\s it and as each perk module
    #: passes it to ``zm_perks::register_perk_basic_info``
    #: (``_zm_perk_juggernaut.gsc:47``).  It is three things at once: the
    #: ``script_noteworthy`` a struct-only machine's entity carries, the key
    #: the module files ``level.machine_assets`` under
    #: (``_zm_perk_juggernaut.gsc:72``), and the argument Der Wunderfizz's
    #: ``zm_perk_random::include_perk_in_random_rotation`` takes.  ``None``
    #: is right for the machines that are not perks -- the pack-a-punch and
    #: the gobblegum machine -- and is what keeps them out of the rotation.
    specialty: str | None = None

    @property
    def needs_module(self) -> bool:
        return self.module is not None

    @property
    def from_prefab(self) -> bool:
        """True when this machine is stamped from a prefab the install ships.

        The others are emitted as the bare struct the framework asks for, so
        code that wants "the model this machine puts in the map" has to ask
        :attr:`placed_model` rather than :attr:`prefab`.
        """
        return self.prefab is not None

    @property
    def placed_model(self) -> str:
        """The ``model`` key this machine's entity carries."""
        model = self.prefab if self.prefab is not None else self.xmodel
        assert model is not None, f"{self.slug} has neither a prefab nor an xmodel"
        return model


PERKS: tuple[PerkKind, ...] = (
    PerkKind(
        "juggernog",
        f"{_CORE_PREFABS}/vending_juggernaut_struct.map",
        r"scripts\zm\_zm_perk_juggernaut",
        ("jugg", "juggernaut", "juggernog", "jug"),
        specialty="specialty_armorvest",
    ),
    PerkKind(
        "speed_cola",
        f"{_CORE_PREFABS}/vending_sleight_struct.map",
        r"scripts\zm\_zm_perk_sleight_of_hand",
        ("speed", "speedcola", "sleight", "sleight_of_hand"),
        specialty="specialty_fastreload",
    ),
    PerkKind(
        "quick_revive",
        f"{_CORE_PREFABS}/vending_revive_struct.map",
        r"scripts\zm\_zm_perk_quick_revive",
        ("revive", "quickrevive"),
        specialty="specialty_quickrevive",
    ),
    PerkKind(
        "double_tap",
        f"{_CORE_PREFABS}/vending_doubletap_struct.map",
        r"scripts\zm\_zm_perk_doubletap2",
        ("doubletap", "double_tap_2", "doubletap2"),
        specialty="specialty_doubletap2",
    ),
    PerkKind(
        "deadshot",
        f"{_CORE_PREFABS}/vending_deadshot_struct.map",
        r"scripts\zm\_zm_perk_deadshot",
        ("deadshot_daiquiri",),
        specialty="specialty_deadshot",
    ),
    PerkKind(
        "stamin_up",
        f"{_CORE_PREFABS}/vending_marathon_struct.map",
        r"scripts\zm\_zm_perk_staminup",
        ("staminup", "stamin-up", "marathon"),
        specialty="specialty_staminup",
    ),
    PerkKind(
        "mule_kick",
        f"{_CORE_PREFABS}/vending_additionalprimaryweapon_struct.map",
        r"scripts\zm\_zm_perk_additionalprimaryweapon",
        ("mulekick", "additionalprimaryweapon"),
        specialty="specialty_additionalprimaryweapon",
    ),
    # -- The two the install ships a script and a model for, but no prefab.
    #
    # Measured on the install.  The comment at ``_zm_perks.gsc:1419``
    # says the struct must carry ``model`` and ``script_noteworthy``, and ``:1437`` collects the machines with
    # ``struct::get_array("zm_perk_machine", "targetname")``.  Everything else
    # the machine needs (its use trigger, its bump trigger and its collision,
    # which is the one shared ``zm_collision_perks1`` model, not a per-machine
    # one) is spawned by that function at runtime.  So a prefab is a
    # convenience, not a requirement, and the three keys below are the whole
    # machine.
    #
    # Both models are stock: ``zone_source/all/assetlist/zm_levelcommon.csv``
    # carries ``xmodel,p7_zm_vending_widows_wine`` and
    # ``xmodel,p7_zm_vending_nuke`` beside ``xmodel,p7_zm_vending_jugg``, and
    # both perk modules are already in that same list as
    # ``scriptparsetree,scripts/zm/_zm_perk_widows_wine.{gsc,csc}`` and
    # ``..._electric_cherry.{gsc,csc}``.  Nothing has to be imported or added
    # to the map's manifest.
    PerkKind(
        "widows_wine",
        None,
        r"scripts\zm\_zm_perk_widows_wine",
        ("widows", "widow", "widowswine", "widows-wine", "wine"),
        xmodel="p7_zm_vending_widows_wine",
        specialty="specialty_widowswine",
    ),
    # Electric Cherry is placeable but it is a Treyarch dev stub, and the
    # stub is what ships: ``_zm_perk_electric_cherry.gsc`` on the install
    # prices it at 10 points, points its HUD shader at
    # ``specialty_quickrevive_zombies``, hands the hint string
    # ``&"ZOMBIE_PERK_WIDOWSWINE"`` (the player is told this is Widow's Wine),
    # substitutes ``p7_zm_vending_nuke`` for the real machine -- the real
    # names are right there commented out -- and, at :118 and :121, sets the
    # spawned machine's ``script_string`` and ``targetname`` to
    # ``marathon_perk`` / ``vending_marathon``, which is Stamin-Up's.  A map
    # that places both gets two machines answering to one name, so the model
    # refuses that pair (``verify.model``).
    #
    # The published fix is an edit to the shipped script, which is a change to
    # the install and not something a map carries.  The map-side alternative
    # is built: :mod:`zmforge.script.perks` writes a perk of our own -- the
    # same ``zm_perks::register_*`` calls, from the map's own script, with its
    # own specialty, price, prompt and machine name -- so a map that wants the
    # effect Electric Cherry never shipped writes one rather than repairing
    # the stub.  ``docs/map-generator-spec.md`` 4.7.1 lists everything wrong
    # with the stub.
    PerkKind(
        "electric_cherry",
        None,
        r"scripts\zm\_zm_perk_electric_cherry",
        ("cherry", "electriccherry", "electric-cherry"),
        xmodel="p7_zm_vending_nuke",
        specialty="specialty_electriccherry",
    ),
    PerkKind(
        "gobblegum",
        f"{_CORE_PREFABS}/vending_bgb_struct.map",
        None,
        ("bgb", "gum", "bubblegum"),
        front_zero=GOBBLEGUM_FRONT_ZERO,
    ),
    PerkKind(
        "pack_a_punch",
        f"{_CORE_PREFABS}/vending_weapon_upgrade_spawnable.map",
        r"scripts\zm\_zm_pack_a_punch",
        ("pap", "packapunch", "pack-a-punch", "weapon_upgrade"),
        front_zero=PACK_A_PUNCH_FRONT_ZERO,
    ),
)

_PERK_INDEX: Mapping[str, PerkKind] = {
    key: perk
    for perk in PERKS
    for key in (perk.slug, *perk.aliases)
}


def perk_named(name: str) -> PerkKind:
    """Look a machine up by slug or by a common community alias."""
    key = str(name).strip().lower().replace(" ", "_")
    try:
        return _PERK_INDEX[key]
    except KeyError:
        raise KeyError(
            f"unknown machine {name!r}; known slugs: "
            + ", ".join(p.slug for p in PERKS)
        ) from None


# --------------------------------------------------------------------------
# Wall weapons
# --------------------------------------------------------------------------
#: Weapon slugs with a stock spawnable-weapon prefab (spec section 4.10).
#:
#: One caveat measured on the install: the chalk drawing inside
#: ``spawnable_weapon_ar_cqb.map`` is ``t7_zm_chalk_buy_hvk30``, and that
#: material is not on the install -- cod2map64 prints ``WARNING: Material
#: 't7_zm_chalk_buy_hvk30' is missing`` and it is the only one of the thirteen
#: chalk materials that does.  An ``ar_cqb`` buy is a working buy with no
#: picture on the wall, so it is banned: it is not in this table, and
#: :func:`wall_weapon_prefab` refuses it by name.
WALL_WEAPONS: tuple[str, ...] = (
    "ar_standard",
    "ar_longburst",
    "ar_marksman",
    "smg_standard",
    "smg_fastfire",
    "smg_versatile",
    "shotgun_pump",
    "pistol_burst",
    "pistol_fullauto",
    "frag_grenade",
    "bouncingbetty",
    "bowie",
)


#: The weapon a ``spawnable_weapon_<slug>`` prefab actually hands over, read
#: off all thirteen prefabs on the install **[measured]**.
#:
#: The slug names the *prefab file*; the weapon is named inside it, by the
#: ``zombie_weapon_upgrade`` key on the buy's ``script_struct``.  For twelve of
#: the thirteen the two strings are the same and the distinction never shows.
#: The thirteenth is ``bowie``, whose struct carries
#: ``"zombie_weapon_upgrade" "bowie_knife"`` -- the row this level's weapon
#: table really has.  So a slug is not a weapon name and must not be looked up
#: in :data:`LEVEL_WEAPONS` as if it were: that is what made ``Z22`` warn on a
#: working buy.
#:
#: The targetname on that struct differs too, and the framework keys off it
#: rather than the slug: eleven prefabs use ``weapon_upgrade``,
#: ``bouncingbetty`` uses ``claymore_purchase`` and ``bowie`` uses
#: ``bowie_upgrade``.  ``_zm_weapons.gsc`` collects all three names (lines 843
#: and 1326-1356 on the install), so all three are wired in stock.
WALL_WEAPON_WEAPONS: Mapping[str, str] = {
    "ar_standard": "ar_standard",
    "ar_longburst": "ar_longburst",
    "ar_marksman": "ar_marksman",
    "smg_standard": "smg_standard",
    "smg_fastfire": "smg_fastfire",
    "smg_versatile": "smg_versatile",
    "shotgun_pump": "shotgun_pump",
    "pistol_burst": "pistol_burst",
    "pistol_fullauto": "pistol_fullauto",
    "frag_grenade": "frag_grenade",
    "bouncingbetty": "bouncingbetty",
    "bowie": "bowie_knife",
}


def wall_weapon_weapon(slug: str) -> str | None:
    """The weapon name behind a wall-buy slug, or ``None`` if it has no prefab.

    ``None`` is the honest answer for a slug outside :data:`WALL_WEAPONS`:
    there is no prefab to read, so nothing can say what it would hand out.
    """
    return WALL_WEAPON_WEAPONS.get(slug)


#: Wall-buy prefabs whose chalk material is missing on the install, mapped to
#: the missing material.  A buy from one of these is a hard error: it works,
#: but the player sees a bare wall with a price prompt and no picture.
CHALKLESS_WALL_WEAPONS: Mapping[str, str] = {
    "ar_cqb": "t7_zm_chalk_buy_hvk30",
}


def wall_weapon_prefab(slug: str) -> str:
    if slug in CHALKLESS_WALL_WEAPONS:
        raise KeyError(
            f"wall weapon {slug!r} is banned: its prefab's chalk material "
            f"{CHALKLESS_WALL_WEAPONS[slug]!r} is missing on the install, so the "
            "buy has no picture on the wall; pick one of: " + ", ".join(WALL_WEAPONS)
        )
    if slug not in WALL_WEAPONS:
        raise KeyError(
            f"unknown wall weapon {slug!r}; known slugs: " + ", ".join(WALL_WEAPONS)
        )
    return f"{_CORE_PREFABS}/spawnable_weapon_{slug}.map"


# The wall-buy family belongs in the table above and is added here instead,
# because its thirteen paths cannot be spelled until WALL_WEAPONS exists.
PREFAB_FRONT_ZERO_BY_MODEL.update(
    {wall_weapon_prefab(slug): WALL_WEAPON_FRONT_ZERO for slug in WALL_WEAPONS}
)


# --------------------------------------------------------------------------
# The weapon set a zm level actually has
# --------------------------------------------------------------------------
# ``_zm_weapons.gsc`` fills ``level.zombie_weapons`` from the string table
# ``gamedata/weapons/zm/zm_levelcommon_weapons.csv``, which every zm level
# gets through ``include,zm_levelcommon_weapons`` in
# ``share/zone_source/zm_levelcommon.zone``.  A usermap that declares no
# weapons of its own has exactly this set and no more, so a name outside it
# is a weapon the map cannot hand out: ``getweapon`` answers, nothing breaks,
# and the feature that asked for it silently does nothing.
#
# Read off the install's own csv (fifty rows, header
# ``weapon_name,upgrade_name,hint,cost,...,in_box,...``).  ``shotgun_olympia``
# is not in it, and not in any assetlist under ``zone_source/*/assetlist``
# either: it is a Black Ops I/II name with no Black Ops III asset.
#: Every weapon name a stock usermap's ``level.zombie_weapons`` holds, mapped
#: to that row's ``in_box`` flag.
LEVEL_WEAPONS: Mapping[str, bool] = {
    "pistol_standard": False,
    "bouncingbetty": False,
    "cymbal_monkey": True,
    "frag_grenade": False,
    "knife": False,
    "bowie_knife": False,
    "ray_gun": True,
    "tesla_gun": True,
    "ar_accurate": True,
    "ar_cqb": True,
    "ar_damage": True,
    "ar_longburst": False,
    "ar_marksman": True,
    "ar_standard": False,
    "lmg_cqb": True,
    "lmg_heavy": True,
    "lmg_light": True,
    "lmg_slowfire": True,
    "pistol_burst": False,
    "pistol_fullauto": False,
    "shotgun_fullauto": True,
    "shotgun_precision": True,
    "shotgun_pump": False,
    "shotgun_semiauto": True,
    "launcher_standard": True,
    "smg_burst": True,
    "smg_capacity": True,
    "smg_fastfire": False,
    "smg_standard": False,
    "smg_versatile": True,
    "sniper_fastbolt": True,
    "sniper_fastsemi": True,
    "sniper_powerbolt": True,
    "zod_riotshield": False,
    "hero_gravityspikes_melee": False,
    "pistol_revolver38": False,
    "octobomb": True,
    "smg_sten": True,
    "raygun_mark3": True,
    "ar_famas": True,
    "ar_garand": True,
    "smg_mp40": True,
    "smg_ppsh": True,
    "special_crossbow_dw": True,
    "ar_peacekeeper": True,
    "pistol_energy": True,
    "shotgun_energy": True,
    "smg_thompson": True,
    "thundergun": True,
    "launcher_multi": True,
}

#: The subset the mystery box can offer: ``in_box`` is the eligibility the
#: chest checks before it hands a candidate over.
BOX_WEAPONS: tuple[str, ...] = tuple(
    name for name, in_box in LEVEL_WEAPONS.items() if in_box
)


# --------------------------------------------------------------------------
# Other stock prefabs and models
# --------------------------------------------------------------------------
BARRICADE_PREFAB = f"{_CORE_PREFABS}/barricade_reciever_wood.map"

#: The debris-hiding variant, and **it is not a drop-in swap**.  Diffed
#: against the plain prefab: the plain file carries a full
#: player ``clip`` brush spanning ``x -48..50`` by ``z 0..113``, which is what
#: plugs the 96 x 112 hole ``add_window`` cuts.  The hide-pieces file does not
#: have that brush at all -- its only collision is a ``clip``/``clip_ai`` pair
#: ``x -39..35`` by ``z 0..35``, the sill band.  Nothing else in this package
#: plugs a barricade opening, so a window built with ``hide_debris=True`` is a
#: 96 x 112 hole a player walks straight through into the yard.  Treyarch use
#: this variant throughout ``zm_giant`` and clip their openings themselves.
#: Check ``Z32`` refuses it until this package does the same.
BARRICADE_PREFAB_HIDE_DEBRIS = f"{_CORE_PREFABS}/barricade_reciever_wood_hide_pieces.map"
MYSTERY_BOX_PREFAB = f"{_CORE_PREFABS}/buyable_magic_box_start.map"
POWER_SWITCH_PREFAB = f"{_CORE_PREFABS}/power_switch.map"

DEFAULT_DOOR_MODEL = "p7_zm_der_door_buy_std_onepiece"
DOOR_MODELS: tuple[str, ...] = (
    DEFAULT_DOOR_MODEL,
    "p7_zm_der_door_buy_med",
    "p7_zm_der_door_buy_std_left",
    "p7_zm_der_door_buy_std_right",
    "p7_zm_der_door_buy_lrg_left",
    "p7_zm_der_door_buy_lrg_right",
)

#: A door leaf's face at ``modelscale 1``: ``(width, height)`` in world units,
#: width along X at yaw 0, standing up from its origin at the base centre.
#: Measured on the mod tools install, two sources agreeing: the vertices of
#: ``model_export/t7_props_zombie/p7_zm_der_door_buy_std_onepiece/*_lod0.XMODEL_BIN``
#: run x -60..60, y -2..2, z 0..102, and the stock collmap
#: ``share/raw/collmaps/p7_zm_der_door_buy_std_onepiece.map`` spans x -60..60,
#: z 0..102.  Only the centred one-piece leaf is here: the other stock leaves
#: are hinged halves whose origin is an edge (collmaps: ``std_left`` x 0..60,
#: ``lrg_left`` x -4..140, ``med`` y -140..0), so they cannot be tiled by
#: centre.  A door using a model not in this table fails check ``Z81``.
#:
#: At scale 1 the leaf covers a 120 x 102 hole and nothing bigger: in the
#: corn maze's 256 x 176 patch gate it left 68 units open at each side and 74
#: over the top, behind an invisible clip wall (the start door read
#: as too small for its opening).  :attr:`~zmforge.blueprint.elements.Door.
#: leaves` scales and tiles the leaf to fill the opening instead.
DOOR_LEAF_SIZE: dict[str, tuple[float, float]] = {
    DEFAULT_DOOR_MODEL: (120.0, 102.0),
}

#: Model names that have linked, for the scatter palette (spec section 4.13).
PROP_PALETTE: tuple[str, ...] = (
    "p7_foliage_grass_02",
    "p7_debris_concrete_rubble_sm_02",
    "p7_crate_wood_01",
)

#: Stock models for furnishing a room by hand, and where each name came from.
#:
#: The mod tools' asset database holds a few thousand models and lives in the
#: tools install; this is the subset whose names can be checked **offline**,
#: which matters because an invented name costs a build to find out about.
#: The first three are :data:`PROP_PALETTE`, recorded by the specification as
#: having linked.  The rest are read out of ``zm_giant.map``, the map source
#: the mod tools ship for The Giant, so the names are stock assets, spelled as
#: that file spells them.  Nothing here has been through a
#: link in *this* package's own build, and the list is short for exactly that
#: reason: it grows when the asset database can be read, not by guessing.
STOCK_PROPS: dict[str, str] = {
    "crate": "p7_crate_wood_01",
    "rubble": "p7_debris_concrete_rubble_sm_02",
    "grass": "p7_foliage_grass_02",
    "teddy_bear": "p7_zm_teddybear",
    # Was "zombie_sign_please_wait", read out of shipped zm_giant.map, which
    # is exactly the risk this docstring warns about: cod2map64 on Windows
    # answered "Missing xmodel 'zombie_sign_please_wait'" / "Missing 1 xmodel!"
    # and wrote no BSP (a test map).  Treyarch ship the map
    # source that references it but not an xmodel for it: no GDT on the install
    # declares that name, while 1,696 other xmodel names are declared.  A
    # shipped map source is therefore not proof that an asset is available to
    # build against.  The replacement was chosen from the 44 sign-like names
    # the install declares and probed through cod2map64 as a misc_model
    # (blueprint/installed.py): a "wash your hands" notice for a zombie
    # outbreak.
    "sign_wash_hands": "p7_zm_der_signage_wash_hands",
    "perk_bottle": "wpn_t7_zmb_perk_bottle_jugg_world",
    "pistol": "t6_wpn_pistol_m1911_world",
    "chain_bracket": "p7_chain_metal_bracket_01",
    "fence_post_cap": "p7_zm_der_chainlink_fence_post_cap",
    "trap_coil": "p7_zm_der_trap_zapper_coil",
    "trap_bracket": "p7_zm_der_trap_bracket",
}

ZOMBIE_BODY_MODEL = "c_zom_test_body1"
DOG_BODY_MODEL = "zombie_wolf"

#: The ``aitype`` a usermap's zombie spawner should be, and the older one the
#: mod tools' level template ships.  Both exist as real assets -- they are
#: entries in ``archetypes/archetypes.gdt`` (``"spawner_zm_factory_zombie"``
#: at :503, ``"spawner_zm_usermap_zombie"`` at :509) -- and the linker
#: resolves either from the ``.map`` entity's classname, so this is a choice
#: between two working spawners and not a fix for a broken one.
#:
#: The usermap one is what Treyarch points a usermap at.  It is the only
#: ``aitype`` line in any zone source the mod tools ship
#: (``share/zone_source/zm_levelcommon.zone:51``: ``aitype,spawner_zm_usermap_zombie``),
#: and the four AI tables it names --
#: ``zm_genesis_zombie.ai_am``/``.ai_ast``/``.ai_asm``/``.ai_bt``,
#: ``archetypes.gdt:346-352`` -- are the only zombie AI tables in that zone
#: (``zone_source/all/assetlist/zm_levelcommon.csv:7170-7173``).
#:
#: The factory one is older and carries fewer animations.  Measured
#: on the install, against our own linked
#: ``usermaps/zm_forge_gate/zone_source/all/assetinfo/zm_forge_gate.csv``:
#: ``spawner_zm_factory_zombie`` drags ``zm_factory_zombie.ai_ast``,
#: ``zm_factory_zombie.ai_am``, ``zm_zombie.ai_asm`` and ``zm_zombie.ai_bt``
#: into the map's own fastfile, and that mapping table names **527**
#: animations against the **635** zombie animations in ``zm_levelcommon``.
#: Of the 140 it does not name, **78 are traversal moves** -- every
#: ``jump_up``/``jump_down``/``jump_across``, every ``mantle_over``, every
#: ``climb_up``, and all nine ``ai_zombie_base_traverse_procedural_*``.  The
#: window traversals (``*_win_trav_*``) are in both, which is why barricades
#: work on the factory spawner and why nothing here noticed: this package does
#: not place traversals yet.
#:
#: **It is not free.**  Measured A/B on the mod tools install, one map
#: (``zm_spawnprobe``, one-room recipe), the classname the only thing changed
#: and the packed output deleted between the two links: the usermap spawner
#: gives ``zm_spawnprobe.ff`` 26,822,848 bytes against the factory spawner's
#: 22,835,904, an assetlist of 1,059 rows against 947 and 650 ``xanim`` rows
#: against 538.  **+3,986,944 bytes and +112 animations.**  Both links had zero
#: ``ERROR`` lines.  The linker duplicates the chain into the map's own
#: fastfile whether or not ``zm_levelcommon`` already holds it, because
#: ``ignore_missing_shipped`` is in the localisation zone and not in this one.
#: So the trade is 4 MB for the traversal moves, not a free upgrade.
#:
#: **Not played.**  The asset graph and the byte counts are measured; that a
#: traversal actually fails on the factory spawner in game is the community
#: claim the graph agrees with, not something
#: observed.
ZOMBIE_SPAWNER_CLASS = "actor_spawner_zm_usermap_zombie"
LEGACY_ZOMBIE_SPAWNER_CLASS = "actor_spawner_zm_factory_zombie"
DOG_SPAWNER_CLASS = "actor_spawner_zm_factory_zombie_dog"


#: The animated chest half of the mystery box (spec section 4.8).  Values are
#: fixed; only the ``script_noteworthy`` name varies per chest.
MAGIC_BOX_BARRIER: tuple[tuple[str, str], ...] = (
    ("classname", "zbarrier_zmcore_MagicBox"),
    ("type", "zmcore_MagicBox"),
    ("barrieranimtime", "0"),
    ("showalternatemodel", "0"),
    ("showupgradedmodel", "0"),
    ("zbarriernumboards", "5"),
    ("zbarrierboardmodel1", "p6_anim_zm_magic_box_fake"),
    ("zbarrierboardmodel2", "p6_anim_zm_magic_box"),
    ("zbarrierboardmodel3", "p6_anim_zm_magic_box"),
    ("zbarrierboardmodel4", "tag_origin"),
    ("zbarrierboardmodel5", "tag_origin"),
    ("zbarrierboardanim1", "o_zombie_magic_box_fake_idle_twitch_a"),
    ("zbarrierboardanim2", "o_zombie_magic_box_leave"),
    ("zbarrierboardanim3", "o_zombie_magic_box_close"),
    ("zbarrierboardanim4", "o_zombie_magic_box_teddy_rise"),
    ("zbarrierboardanim5", "o_zombie_magic_box_teddy_rise"),
    ("zbarriertearanim1", "o_zombie_magic_box_fake_idle_twitch_b"),
    ("zbarriertearanim2", "o_zombie_magic_box_arrive"),
    ("zbarriertearanim3", "o_zombie_magic_box_open"),
    ("zbarriertearanim4", "o_zombie_magic_box_weapon_rise"),
    ("zbarriertearanim5", "o_zombie_magic_box_weapon_dual_rise"),
)

DEFAULT_CHEST_NAME = "start_chest"
DEFAULT_CHEST_COST = 950


# --------------------------------------------------------------------------
# Der Wunderfizz
# --------------------------------------------------------------------------
#: The machine that sells a random perk.  Read off the install,
#: out of ``share/raw/scripts/zm/_zm_perk_random.{gsc,csc,gsh}``.
#:
#: It is **not a perk** and does not go through the perk-machine mechanism.
#: ``_zm_perks.gsc:1437`` collects perk machines with
#: ``struct::get_array("zm_perk_machine", "targetname")`` -- *structs* -- and
#: spawns the trigger and the collision itself.  Der Wunderfizz is collected
#: with ``_zm_perk_random.gsc:91``
#: ``level.perk_random_machines = GetEntArray( "perk_random_machine",
#: "targetname" )`` -- *entities* -- and every line that follows drives it as
#: a zbarrier: ``ShowZBarrierPiece``, ``HideZBarrierPiece``,
#: ``SetZBarrierPieceState`` and ``GetNumZBarrierPieces``
#: (``_zm_perk_random.gsc:843-910``), and its clientfields are registered on
#: the ``"zbarrier"`` entity type (``:49-51``).  So it is authored the way
#: the mystery box is, as a ``zbarrier_*`` entity with its pieces spelled out
#: in keys, not as a table row beside the perks.
#:
#: **Nothing has to be imported.**  ``zone_source/all/assetlist/
#: zm_levelcommon.csv`` already carries ``xmodel,p7_zm_vending_wonder``
#: (:1990), all three script halves as ``scriptparsetree,
#: scripts/zm/_zm_perk_random.{gsh,gsc,csc}`` (:7053-7055) and the four
#: effects the two halves precache themselves --
#: ``fx,dlc1/castle/fx_wonder_fizz_light_{green,red,yellow}`` (:6584-6586)
#: and ``fx,zombie/fx_wonder_fizz_lightning_all`` (:6880).  The ``#precache``
#: lines live in Treyarch's own files (``_zm_perk_random.csc:19-22``), so the
#: map declares no asset and precaches nothing.  This is the same argument
#: as the one for the struct-only perks above, and it is the reason a
#: missing file in ``map_source/_prefabs`` proves nothing: there is no
#: Wunderfizz prefab on the mod tools install and none is needed.
WUNDERFIZZ_TARGETNAME = "perk_random_machine"

#: One machine has to carry this, or the Wunderfizz never starts.
#: ``init_starting_perk_random_machine_location`` (``_zm_perk_random.gsc:
#: 123-150``) threads ``machine_think()`` on the *first* machine whose
#: ``script_noteworthy`` contains it and sends every other machine to
#: ``wait_for_power()``, so a map with none has machines and no logic.
WUNDERFIZZ_START_NOTEWORTHY = "start_perk_random_machine"

#: The zbarrier the entity is spelled as.  The six piece indices the stock
#: script drives (``_zm_perk_random.gsh:26-31``) need a six-piece barrier,
#: and ``zmcore_packapunch`` is the six-piece one the mod tools install has a real
#: definition for (``source_data/zbarriers.gdt:449``, ``numAttackSlots 1``,
#: the same as the pack-a-punch's own prefab carries).  Every board model and
#: every animation is overridden by the keys below, which is what Treyarch's
#: own ``vending_weapon_upgrade_spawnable.map:261-285`` does to the same
#: definition, so the name is the piece count and nothing else.
#:
#: It is also why nothing goes in the manifest: ``zm_mymap.zone``
#: declares no ``zbarrier`` line and its ``zbarrier_zmcore_MagicBox`` links,
#: so the entity's keys, not the zone, are what build the barrier.
WUNDERFIZZ_ZBARRIER_TYPE = "zmcore_packapunch"
WUNDERFIZZ_CLASSNAME = f"zbarrier_{WUNDERFIZZ_ZBARRIER_TYPE}"

#: The only Wunderfizz model the mod tools install has.
WUNDERFIZZ_MODEL = "p7_zm_vending_wonder"

#: The six pieces, in the order ``_zm_perk_random.gsh:26-31`` indexes them
#: (piece 0 is board 1).  Three of them -- ON_OFF, AVAILABLE and IDLE -- are
#: the machine body in three animation states, and ``process_perk_random_
#: machine_state`` (``_zm_perk_random.gsc:843-910``) shows at least one of
#: those three in every one of its seven states, so putting the body on all
#: three is what keeps the machine visible throughout.  The ball and the
#: bottle tag are ``tag_origin``: the mod tools install ships one Wunderfizz model
#: and no Wunderfizz animation at all (no ``xanim`` row in
#: ``zm_levelcommon.csv`` matches, and the ball is part of DLC1's own
#: assets), so the machine that comes out is **static**.  Blank animations
#: are deliberate and are spelled the way the definition itself spells an
#: empty slot (``zbarriers.gdt`` ``"boardModel6" ""``): left out, each piece
#: would inherit a pack-a-punch animation.
WUNDERFIZZ_PIECES: tuple[str, ...] = (
    "tag_origin",        # 0  ZM_PERK_RANDOM_BALL_ON_OFF_PIECE_INDEX
    WUNDERFIZZ_MODEL,    # 1  ZM_PERK_RANDOM_BODY_ON_OFF_PIECE_INDEX
    WUNDERFIZZ_MODEL,    # 2  ZM_PERK_RANDOM_BODY_AVAILABLE_PIECE_INDEX
    WUNDERFIZZ_MODEL,    # 3  ZM_PERK_RANDOM_BODY_IDLE_PIECE_INDEX
    "tag_origin",        # 4  ZM_PERK_RANDOM_BOTTLE_TAG_PIECE_INDEX
    "tag_origin",        # 5  ZM_PERK_RANDOM_BALL_SPIN_PIECE_INDEX
)

#: Which way ``p7_zm_vending_wonder`` faces at yaw 0.  **Not measured**: the
#: model has never been opened here and this is the perk family's zero
#: (:data:`PERK_FRONT_ZERO`) borrowed.  Worth knowing before it is:
#: the use trigger is not in front of the machine either way.
#: ``create_perk_random_machine_unitrigger_stub`` (``_zm_perk_random.gsc:
#: 152-170``) puts it at ``self.origin + AnglesToRight( self.angles ) * 40``,
#: i.e. 40 units off the machine's *right*, where every other machine's
#: trigger is a radius around the machine itself.
WUNDERFIZZ_FRONT_ZERO: Facing = PERK_FRONT_ZERO

#: What the stock script charges when the entity says nothing:
#: ``ZM_PERK_RANDOM_COST`` in ``_zm_perk_random.gsh:33``, applied at
#: ``_zm_perk_random.gsc:102-106``.  There is no established map key for it,
#: so a placed Wunderfizz costs this and the emitter writes no price.
WUNDERFIZZ_COST = 1500

#: The module both scripts must name, server and client, the same way a
#: perk's module is named in both (check Z9).
WUNDERFIZZ_MODULE = r"scripts\zm\_zm_perk_random"


# --------------------------------------------------------------------------
# Spawn-set matching
# --------------------------------------------------------------------------
#: The gametypes whose spawn-match string the framework may build.
SPAWN_GAMETYPES: tuple[str, ...] = ("zclassic", "zcleansed", "zgrief")

#: ``level.default_start_location`` as the framework sets it.  The map script
#: must never assign anything else (spec section 4.1, K2).
START_LOCATION = "start_room"


def spawn_string_tokens(location: str = START_LOCATION) -> str:
    """The ``script_string`` value that makes one spawn set serve every mode."""
    return " ".join(f"{mode}_{location}" for mode in SPAWN_GAMETYPES)


# --------------------------------------------------------------------------
# Stock models that are half of an assembly
# --------------------------------------------------------------------------
#: Models Treyarch never places on their own, and the parts that go with them.
#:
#: A stock ``xmodel`` name reads like a whole object and sometimes is not.
#: ``p7_cai_staircase_01`` is the **frame** of a staircase -- two stringers, a
#: handrail each side and a glass balustrade -- and its treads are a separate
#: model, ``p7_cai_staircase_step_01``, placed once per step.  Put the frame in
#: a map by itself and the game draws handrails standing in mid air with
#: nothing between them.  Nothing objects: the model exists, it
#: packs, ``cod2map64`` and the linker are silent, and the assetlist says the
#: xmodel and both its materials went into the fastfile.  The only evidence
#: that a part is missing is Treyarch's own use of the pair.
#:
#: Offsets are the companion's origin minus the frame's origin, at yaw 0, read
#: off the install's own prefab
#: ``map_source/_prefabs/mp/mp_combine/geo/mp_combine_aquaculture_bdg_south/
#: mp_combine_lab_staircase.map``: the frame sits at
#: ``-58 6 40`` and eleven ``p7_cai_staircase_step_01`` entities follow at
#: ``-58 13 46`` .. ``-58 133 126``, which is ``+12`` along Y and ``+8`` in Z
#: per tread.  ``map_source/_prefabs/mp/mp_sector/.../mp_sector_lab_staircase.map``
#: is the same eleven entities at the same offsets.
#:
#: The rotation sense is measured off the same corpus rather than assumed:
#: ``mp_combine_aquaculture_bdg_north_outdoor_staircase.map`` carries four
#: treads at ``angles "0 270 0"`` climbing in **+X**, and
#: ``mp_combine_external_deck_area.map`` carries five at ``"0 90 0"`` climbing
#: in **-X**.  Both agree with the counter-clockwise turn
#: :func:`prefab_yaw` already records, so a run authored along +Y at yaw 0
#: rotates with the entity.
MODEL_COMPANIONS: Mapping[str, tuple[tuple[str, tuple[float, float, float]], ...]] = {
    "p7_cai_staircase_01": tuple(
        ("p7_cai_staircase_step_01", (0.0, 7.0 + 12.0 * index, 6.0 + 8.0 * index))
        for index in range(11)
    ),
}


def companions_of(model: str) -> tuple[tuple[str, tuple[float, float, float]], ...]:
    """The parts ``model`` is never shipped without, as ``(model, offset)``."""
    return MODEL_COMPANIONS.get(model, ())


def companion_origins(
    model: str,
    origin: tuple[float, float, float],
    yaw: float,
    scale: float = 1.0,
) -> tuple[tuple[str, tuple[float, float, float]], ...]:
    """Where each of ``model``'s companion parts goes, for a prop at ``yaw``.

    The offsets are authored at yaw 0 and turned counter-clockwise, which is
    the sense :func:`prefab_yaw` records and the stock prefabs above confirm.
    ``scale`` is the frame's ``modelscale``: the parts take the same one, so
    the run between them has to grow with it.
    """
    from math import cos, radians, sin

    angle = radians(yaw)
    cosine, sine = cos(angle), sin(angle)
    x, y, z = origin
    placed: list[tuple[str, tuple[float, float, float]]] = []
    for part, (dx, dy, dz) in companions_of(model):
        dx, dy, dz = dx * scale, dy * scale, dz * scale
        # Rounded because a quarter turn leaves 1e-15 where a zero belongs,
        # and a map's numbers are read by people as well as by cod2map64.
        placed.append(
            (
                part,
                (
                    round(x + dx * cosine - dy * sine, 3) + 0.0,
                    round(y + dx * sine + dy * cosine, 3) + 0.0,
                    round(z + dz, 3) + 0.0,
                ),
            )
        )
    return tuple(placed)


# --------------------------------------------------------------------------
# Models that are not objects
# --------------------------------------------------------------------------
#: Words in a stock model's name that say the model depicts a **route**.
#:
#: WHY A ROUTE IS NOT LIKE THE REST OF THE PALETTE.  Every other model a map
#: places is an object: the player looks at it, walks round it, and is done.
#: A staircase is not an object, it is an **instruction**.  A player who sees
#: one reads "that is the way up", walks to it, and is owed a floor at the
#: top.  Nothing in a generated map can keep that promise with a model: a
#: prop is drawn, and its collision -- when it has any at all -- is the box
#: ``cod2map64`` bakes from a collmap, not a set of treads.  Every route in a
#: map this package builds is brushwork
#: (:meth:`~zmforge.blueprint.model.Blueprint.add_steps`, guarded by ``Z19``),
#: so a route-shaped *model* is a promise the map cannot keep wherever it
#: came from.
#:
#: Screening the name rather than keeping an allow-list is deliberate.  A
#: hand-classified table of every model in a palette is a table that goes
#: stale the first time somebody adds one; a screen on the name catches the
#: next ``..._staircase_02`` on the day it is added.  The palettes are stock
#: Treyarch models and their names describe them.
ROUTE_WORDS: tuple[str, ...] = (
    "staircase",
    "stairs",
    "stairway",
    "stepladder",
    "ladder",
    "ramp",
    "escalator",
)

#: Judgements about a single model that its name does not carry.  ``True``
#: means "this is a route although the name does not say so"; ``False`` means
#: "the name trips :data:`ROUTE_WORDS` and the model is not a route".  Empty
#: for now; it exists so that a judgement is recorded beside its reason rather
#: than argued from a substring.
ROUTE_MODELS: Mapping[str, bool] = {}


#: How far up a route model actually delivers a player, above its own origin,
#: for the ones where nothing else in this package can work it out.
#:
#: This is the **top of the climb**, not the top of the model.  A staircase's
#: bounding box includes its handrail and a ladder's includes its stiles; what
#: the player arrives at is the last tread or the last rung, and a check that
#: used the box would demand a floor above the handrail.  A model whose parts
#: are in :data:`MODEL_COMPANIONS` does not need a row here --
#: :func:`route_top` reads the highest part's offset instead, which is the
#: same number measured rather than typed.
ROUTE_TOP: Mapping[str, float] = {
    # The stock Der Eisendrache teleporter ladder, from the converted asset's
    # own bounding box: it has no separate rung models to read.
    "p7_zm_der_teleporter_mf_ladder": 50.7,
}


def is_route_model(name: str) -> bool:
    """Whether ``name`` depicts a way to get somewhere rather than an object."""
    if name in ROUTE_MODELS:
        return ROUTE_MODELS[name]
    lowered = name.lower()
    return any(word in lowered for word in ROUTE_WORDS)


def route_top(name: str, scale: float = 1.0) -> float | None:
    """How far above its origin ``name`` delivers a player, or ``None``.

    ``None`` means nobody has measured this model's climb, which is a thing a
    check reports rather than guesses at: a route whose top is unknown cannot
    be shown to lead anywhere.
    """
    parts = MODEL_COMPANIONS.get(name)
    if parts:
        return max(offset[2] for _part, offset in parts) * scale
    height = ROUTE_TOP.get(name)
    return None if height is None else height * scale
