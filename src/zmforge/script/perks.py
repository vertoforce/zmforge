r"""Perks of our own: everything a map emits to sell one the game does not have.

A stock perk is nine files in the install.  A perk of ours is **script the map
already ships, one ``script_struct`` and one line in the map's own ``.str``**,
and nothing else: no ``.gdt`` entity, no image, no sound bank, no effect file
and no change to anybody's install.  That is possible because
``scripts\zm\_zm_perks`` is a registration API rather than a table -- Treyarch's
own doc block above ``register_perk_basic_info`` says the specialty string
must be unique and is how system scripts identify the perk
(``_zm_perks.gsc:1808-1818``) -- and because every asset a perk *shows* is
already on the level-common list and free to name.

**Nothing here is written by anybody but us, and nothing is taken from a
published map.**  The names, the prices, the prompts and the effects are this
repository's.  Where a community perk is known to do something similar, the
effect here is written from the stock scripts rather than read off theirs.

WHAT THE MAP EMITS, and where each half was read (the mod tools install,
``share/raw/scripts``):

* **Five registration calls**, in a function of the map's own, called from
  :attr:`~zmforge.script.custom.Slot.BEFORE_ENTRY`.  The framework's own
  ``zm_perks::init`` reads what they wrote, and it runs inside the framework
  entry (``_zm_perks.gsc:40`` ``default_vending_precaching()``), so before the
  entry is the window.  Each call keeps the *first* registration
  (``_zm_perks.gsc:1903``, ``:1926``, ``:1959``, ``:1987`` are all
  ``if ( !isdefined( ... ) )``), which is why a map cannot take a stock perk
  over -- and why a specialty nothing else registers is ours outright.
* **One ``script_struct``** carrying ``targetname zm_perk_machine``, the
  specialty in ``script_noteworthy`` and the machine's ``model``.  That is the
  whole map side; ``perk_machine_spawn_init`` spawns the use trigger, the bump
  trigger and the collision itself.  :class:`~zmforge.blueprint.elements.Machine`
  already emits exactly this for Widow's Wine, so a perk of ours is placed with
  the same call and gets the same reachability and clearance checks.
* **One localized string**, which is the buy prompt.  ``SetHintString( hint,
  cost )`` (``_zm_perks.gsc:395``, ``:530``) passes the cost as ``&&1``, the
  same shape a wall buy uses, so :mod:`zmforge.emit.strings` writes both.

WHAT IT CANNOT HAVE, and both limits are real:

* **No jingle.**  The machine's jingle and sting are sound *aliases*
  (``_zm_perk_juggernaut.gsc:90``, ``:92``, played by ``_zm_audio.gsc:1607``
  with no ``isdefined`` guard), and a usermap on the mod tools install has no perk
  aliases at all -- ``share/raw/sound/aliases`` holds one row, ``test_sound``.
  A stock machine in a usermap here is already silent, so ours is silent in
  exactly the same way and for the same reason.  The alias is still *named*,
  because the unguarded read is what would fault.
* **No icon of its own without claiming a slot.**  The heads-up icon is drawn
  by a hard-coded table inside the shipped interface widget, which is Lua this
  install's linker refuses to pack (``ERROR: Lua not supported``, measured).  Eleven keys are bound in that table and nine belong to perks
  with a module.  The other two -- ``tombstone`` and ``dive_to_nuke`` -- name
  images that are **in no stock asset list**, so nothing draws in them
  and a map that ships art under those names owns the slot.  See
  :data:`UNCLAIMED_ICON_SLOTS`.

**None of this has been played.**  Every claim above is a property of the
install's own scripts or of the text a commit writes.  A perk that links is not
a perk that works.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..spatial import Facing
from .custom import CustomFunction, CustomScript, Slot

__all__ = [
    "SPECIALTY_PREFIX",
    "IconSlot",
    "TOMBSTONE_ICON",
    "DIVE_TO_NUKE_ICON",
    "UNCLAIMED_ICON_SLOTS",
    "BOUND_ICON_SLOTS",
    "ICON_PATH_PREFIX",
    "icon_key_of",
    "icon_named",
    "STOCK_BOTTLES",
    "STOCK_MACHINE_MODELS",
    "STOCK_MACHINE_LIGHTS",
    "PerkEffect",
    "CustomPerk",
    "perk_script",
    "points_each_round",
    "move_speed",
    "COIN_RETURN",
    "coin_return",
]

_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")

#: The prefix every perk of ours puts on its specialty string.  Nothing in the
#: game counts perks or validates the name -- the thirteen ``specialty_``
#: strings in ``_zm_perks.gsh:22-34`` are ``#define`` lines, not a registry --
#: so the only requirement is that no other registration uses the same string,
#: and the first registration wins.  The prefix is how a reader of a console
#: log tells our perk from a shipped one.
SPECIALTY_PREFIX = "specialty_zmf_"

#: The nine perk bottles on the stock asset list
#: (``zone_source/all/assetlist/zm_levelcommon.csv:6283-6291``).  Naming one
#: costs a map nothing: the weapon is in the level-common zone whether or not
#: anything drinks it.  Building a new one is possible and is a different job
#: -- see ``docs/how-zombies-maps-work.md``, "The bottle".
STOCK_BOTTLES: tuple[str, ...] = (
    "zombie_perk_bottle_additionalprimaryweapon",
    "zombie_perk_bottle_cherry",
    "zombie_perk_bottle_deadshot",
    "zombie_perk_bottle_doubletap",
    "zombie_perk_bottle_jugg",
    "zombie_perk_bottle_marathon",
    "zombie_perk_bottle_revive",
    "zombie_perk_bottle_sleight",
    "zombie_perk_bottle_widows_wine",
)

#: The vending machine models on the stock asset list (same file, ``:1978-1990``).
#: ``p7_zm_vending_nuke`` is the default because nothing places it: it is the
#: model the Electric Cherry dev stub names, and that stub ships no machine.
STOCK_MACHINE_MODELS: tuple[str, ...] = (
    "p7_zm_vending_ads",
    "p7_zm_vending_deadshot",
    "p7_zm_vending_doubletap2",
    "p7_zm_vending_jugg",
    "p7_zm_vending_marathon",
    "p7_zm_vending_nuke",
    "p7_zm_vending_revive",
    "p7_zm_vending_sleight",
    "p7_zm_vending_three_gun",
    "p7_zm_vending_widows_wine",
)

#: The perk machine lights on the stock asset list (same file, ``:6810-6823``).
#: The effect is a *handle*: the perk's precache function writes
#: ``level._effect[ <own name> ] = "<path>"`` and ``_zm_perks.gsc:302`` plays
#: it back, so naming a stock path is free and building a new ``.efx`` is not.
STOCK_MACHINE_LIGHTS: tuple[str, ...] = (
    "zombie/fx_perk_daiquiri_factory_zmb",
    "zombie/fx_perk_doubletap2_zmb",
    "zombie/fx_perk_juggernaut_zmb",
    "zombie/fx_perk_mule_kick_zmb",
    "zombie/fx_perk_quick_revive_zmb",
    "zombie/fx_perk_sleight_of_hand_zmb",
    "zombie/fx_perk_stamin_up_zmb",
    "zombie/fx_perk_widows_wine_zmb",
)


# --------------------------------------------------------------------------
# The icon
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class IconSlot:
    """One key in the shipped HUD widget's table, and the image it draws.

    ``path`` is the UI-model path a perk writes with
    ``clientfield::set_player_uimodel``; ``image`` is the name the widget
    resolves at run time (``PerkImage:setImage( RegisterImage( image ) )``),
    which is why a map can own the slot by shipping an image asset under that
    name.  ``evidence`` is where the pair was read.
    """

    key: str
    path: str
    image: str
    evidence: str


#: The two bound keys the game ships no art for.  Both are read out of the
#: published decompile of ``ZMPerksContainerFactory.lua`` (PC_Ship_2025-05-31),
#: and ``grep -rn "tombstone\|divetonuke" zone_source/all/assetlist/*.csv`` on
#: the mod tools install returns **nothing**, which is what makes them unclaimed: a
#: widget that will draw, with no picture behind it.  Taking one costs the map
#: nothing, because no stock perk in a usermap lights them either.  The
#: decompile is read for reference only: the mod tools ship no source for this
#: widget, and only its key names, which are identifiers, are used here.
TOMBSTONE_ICON = IconSlot(
    "tombstone",
    "hudItems.perks.tombstone",
    "specialty_tombstone_zombies",
    'ZMPerksContainerFactory.lua, key tombstone = "specialty_tombstone_zombies"; '
    "no image of that name in any zone_source assetlist on the mod tools install "
    ".  The path is also _zm_perks.gsh:16 "
    "PERK_CLIENTFIELD_TOMBSTONE",
)

DIVE_TO_NUKE_ICON = IconSlot(
    "dive_to_nuke",
    "hudItems.perks.dive_to_nuke",
    "specialty_divetonuke_zombies",
    'ZMPerksContainerFactory.lua, key dive_to_nuke = "specialty_divetonuke_zombies"; '
    "not one of the thirteen PERK_CLIENTFIELD_ defines and not on any "
    "assetlist on the mod tools install",
)

#: Both of them, in the order a map should take them.
UNCLAIMED_ICON_SLOTS: tuple[IconSlot, ...] = (TOMBSTONE_ICON, DIVE_TO_NUKE_ICON)

#: Every key the shipped widget binds, and the stock perk that lights it, or
#: ``None`` for the two nothing lights.  Read off the published decompile of
#: ``ZMPerksContainerFactory.lua`` (PC_Ship_2025-05-31, eleven keys) against
#: the ``PERK_CLIENTFIELD_*`` defines in ``_zm_perks.gsh:7-19`` and each
#: module's own setter.  It is here so a check can answer one question: is the
#: slot this map is claiming already somebody's?
BOUND_ICON_SLOTS: dict[str, str | None] = {
    "additional_primary_weapon": "specialty_additionalprimaryweapon",
    "dead_shot": "specialty_deadshot",
    "dive_to_nuke": None,
    "doubletap2": "specialty_doubletap2",
    "electric_cherry": "specialty_electriccherry",
    "juggernaut": "specialty_armorvest",
    "marathon": "specialty_staminup",
    "quick_revive": "specialty_quickrevive",
    "sleight_of_hand": "specialty_fastreload",
    "tombstone": None,
    "widows_wine": "specialty_widowswine",
}

#: The path a key is written under, which is the ``.gsh`` spelling.
ICON_PATH_PREFIX = "hudItems.perks."


def icon_key_of(path: str) -> str | None:
    """The widget key a UI-model path names, or ``None`` if it is not one."""
    text = str(path)
    if not text.startswith(ICON_PATH_PREFIX):
        return None
    return text[len(ICON_PATH_PREFIX) :]

_ICONS = {slot.key: slot for slot in UNCLAIMED_ICON_SLOTS}


def icon_named(key: str) -> IconSlot:
    """An unclaimed slot by key, or a refusal naming the two there are."""
    try:
        return _ICONS[str(key).strip().lower()]
    except KeyError:
        raise KeyError(
            f"unknown icon slot {key!r}; the shipped interface binds eleven "
            "keys and nine belong to perks with a module, so the two a map "
            "may take are: " + ", ".join(_ICONS)
        ) from None


# --------------------------------------------------------------------------
# The effect
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PerkEffect:
    """What holding the perk actually does, as the body of two functions.

    ``give`` is threaded on the player when the perk is bought and re-threaded
    when it comes back after a pause (``_zm_perks.gsc:753``, ``:1289``);
    ``take`` is called on the player when it is lost or paused (``:947``,
    ``:1255``).  Neither needs to end the other: :func:`perk_script` writes the
    ``endon``/``notify`` pair around them, which is the contract the framework
    documents -- a give thread ends on ``<specialty>_stop`` and a take thread
    sends it.

    ``using`` names every module the bodies call into, so the emitted script
    carries the ``#using`` lines its own text needs.  ``evidence`` is where
    each call was read, and it is not decoration: every namespaced call in the
    bodies has to be in :mod:`zmforge.script.symbols` or the script check
    refuses the map.
    """

    summary: str
    give: tuple[str, ...]
    take: tuple[str, ...] = ()
    using: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a perk effect needs a one-line summary")
        if not self.give:
            raise ValueError(
                "a perk effect with no give body is a machine that takes the "
                "points and does nothing"
            )


def points_each_round(points: int) -> PerkEffect:
    """Pay the holder ``points`` at the start of every round.

    The simplest honest effect there is: one stock notify, one stock scoring
    call, nothing to undo when the perk is lost, and a player can see whether
    it worked by reading their own score.

    * ``_zm.gsc:4433`` ``level notify( "start_of_round" );`` is the notify,
      and ``zm_giant.gsc:787`` is a shipped map waiting on it the same way.
    * ``_zm_score.gsc:521`` ``function add_to_player_score( points,
      b_add_to_total, str_awarded_by )`` adds to the player's score and to the
      HUD, and rounds the number up to ten at ``:528``.

    **Unplayed.**  What is checked here is that the text says this.
    """
    amount = int(points)
    if amount <= 0:
        raise ValueError(
            f"a dividend of {amount} points is not an effect; "
            "zm_score::add_to_player_score rounds up to 10 and a perk that "
            "pays nothing is a machine that only takes"
        )
    return PerkEffect(
        summary=f"pays the holder {amount} points at the start of every round",
        give=(
            "for ( ;; )",
            "{",
            '\tlevel waittill( "start_of_round" );',
            f"\tself zm_score::add_to_player_score( {amount} );",
            "}",
        ),
        using=(r"scripts\zm\_zm_score",),
        evidence=(
            '_zm.gsc:4433 level notify( "start_of_round" )',
            "_zm_score.gsc:521 function add_to_player_score( points, "
            "b_add_to_total, str_awarded_by )",
        ),
    )


def move_speed(percent_faster: float) -> PerkEffect:
    """Move the holder ``percent_faster`` per cent faster than base, and put it
    back when the perk goes.

    **What actually moves the player**, read on the mod tools install:
    ``SetMoveSpeedScale`` is an engine call on a player and the stock scripts
    use it as a *scale on base movement*, not as a speed in units --
    ``zm_usermap.gsc:336`` ``self SetMoveSpeedScale( 1 );`` is what a usermap
    sets on every player it spawns, ``_zm.gsc:4795`` ``self
    setMoveSpeedScale( 0.3 );`` is what a zombified player gets, and
    ``_loadout.gsc:1140`` multiplies the current value by a modifier.  So 1 is
    this game's normal and ``1 + percent/100`` is the target.

    **Stamin-Up is not this mechanism and cannot be borrowed.**
    ``_zm_perk_staminup.gsc`` is 90 lines and *none* of them touch movement:
    it registers, precaches, sets a clientfield and dresses a machine.  The
    boost is applied engine-side off the specialty string
    ``specialty_staminup`` (``_zm_perks.gsh:27``), and a perk of ours
    registers a specialty of its own, which nothing in the engine knows.  That
    is why this effect is a scale call and not a perk grant -- and it is also
    why **whether the two stack, and how, has not been measured**.  A map that
    places Stamin-Up and this perk hands the player two changes to the same
    number from two different places.

    **Also unmeasured: whether the engine clamps the scale.**  The three stock
    values read above are 0.3, 1 and a multiply; nothing in the shipped
    scripts sets one above 1, so a scale above 1 is untested text.  If the
    engine clamps, the failure is a player who is faster than base but not by
    this much.

    **The spawn path resets it**, which is why the give body loops rather than
    setting the scale once.  ``giveCustomCharacters``
    (``zm_usermap.gsc:276``, ``:336``) runs from ``giveLoadoutLevelSpecific``
    (``_globallogic_spawn.gsc:176-178``) inside ``spawnPlayer``, and that
    function sends ``spawned_player`` at ``:464``, after a
    ``waittillframeend`` -- so a re-apply on that notify lands after the reset
    rather than before it.

    ``take`` puts the scale back to 1, which is the value the spawn path
    itself writes, so a player who loses the perk is a player the stock
    scripts would have made.

    **Unplayed.**  What is checked here is that the text says this.
    """
    percent = float(percent_faster)
    if percent <= 0.0:
        raise ValueError(
            f"a speed perk that makes the player {percent:g}% faster is not an "
            "effect: SetMoveSpeedScale takes a scale on base movement and 1 is "
            "what zm_usermap.gsc:336 already sets on every spawn, so anything "
            "at or below 0% is a machine that charges for the walk the player "
            "already has"
        )
    scale = f"{1.0 + percent / 100.0:g}"
    return PerkEffect(
        summary=(
            f"moves the holder {percent:g}% faster than base "
            f"(SetMoveSpeedScale {scale}) for as long as they hold it"
        ),
        give=(
            f"// {scale} is a scale on base movement, not a speed: "
            "zm_usermap.gsc:336 sets",
            "// this player's scale to 1 on every spawn and _zm.gsc:4795 sets "
            "0.3 on a",
            "// zombified one, so 1 is this game's normal.",
            f"self SetMoveSpeedScale( {scale} );",
            "for ( ;; )",
            "{",
            "\t// The spawn path writes the scale back to 1 "
            "(zm_usermap.gsc:336, reached",
            "\t// from _globallogic_spawn.gsc:176-178), and sends this notify "
            "afterwards",
            "\t// at :464, so re-applying here lands after the reset.",
            '\tself waittill( "spawned_player" );',
            f"\tself SetMoveSpeedScale( {scale} );",
            "}",
        ),
        take=(
            "// Back to the value the spawn path itself writes "
            "(zm_usermap.gsc:336).",
            "self SetMoveSpeedScale( 1 );",
        ),
        evidence=(
            "zm_usermap.gsc:336 self SetMoveSpeedScale( 1 ); on every player "
            "the usermap spawns",
            "_zm.gsc:4795 self setMoveSpeedScale( 0.3 ); on a zombified player",
            "_zm_perk_staminup.gsc: 90 lines, no movement call at all, so the "
            "stock boost is engine-side off specialty_staminup "
            "(_zm_perks.gsh:27) and cannot be reached by a specialty of ours",
            "_globallogic_spawn.gsc:176-178 giveLoadoutLevelSpecific calls "
            'giveCustomCharacters, :464 self notify( "spawned_player" ) after '
            "waittillframeend",
        ),
    )


# --------------------------------------------------------------------------
# The perk
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CustomPerk:
    """One perk of this repository's own: its name, its price and its effect.

    Every field a recipe writes is here, and the derived names -- the specialty
    string, the alias the power switch notifies on, the machine's Radiant name
    and the five function names -- are built from the slug, so two perks cannot
    collide by accident.

    ``bottle`` has no default on purpose in spirit and a stock default in
    practice: the drink is **mandatory**.  ``_zm_perks.gsc:594-620`` takes the
    points, gives the bottle, switches to it, and grants the perk only if the
    weapon change completes, so a perk whose bottle does not resolve is a
    machine that charges the player and hands back nothing.  The default is the
    Electric Cherry bottle, which is on the stock list and which no working
    perk uses, because the shipped Electric Cherry is a dev stub.
    """

    slug: str
    name: str
    cost: int
    effect: PerkEffect
    bottle: str = "zombie_perk_bottle_cherry"
    machine_model: str = "p7_zm_vending_nuke"
    #: Units to move the framework's use trigger out of the machine's front
    #: (``AnglesToRight`` of its angles is the front: perks face south at yaw
    #: 0).  The trigger is a 40-unit radius at the origin
    #: (``_zm_perks.gsc:1513``), which a vending machine's front reaches and
    #: a car's side does not.
    trigger_shift: float = 0.0
    #: Which way the machine model's front looks at yaw 0.  Vending machines
    #: face south; a model built otherwise (a fridge's door is on its +x, so
    #: ``Facing.EAST``) says so here, and both the placed yaw and the
    #: ``trigger_shift`` direction follow it.
    front_zero: Facing = Facing.SOUTH
    icon: IconSlot | None = TOMBSTONE_ICON
    light_fx: str = "zombie/fx_perk_stamin_up_zmb"
    #: The jingle and sting stamped on the use trigger.  Stock alias names,
    #: and silent: a usermap on the mod tools install has no perk sound aliases at all,
    #: so this is what a stock machine in a usermap gets.  Named rather
    #: than left out because ``_zm_audio.gsc:1607`` reads ``self.script_sound``
    #: with no ``isdefined`` guard.
    jingle: str = "mus_perks_stamin_jingle"
    sting: str = "mus_perks_stamin_sting"
    #: Opt-in: a key into :data:`zmforge.texture.hud_icons.ART`.  When set,
    #: declaring the perk also ships that picture as the image asset named
    #: ``icon.image``, so the slot draws it instead of nothing (the "a map
    #: that ships art under those names owns the slot" route above).  ``None``
    #: is the default and ships no image, which is every map before this.
    icon_art: str | None = None

    def __post_init__(self) -> None:
        if self.icon_art is not None:
            if self.icon is None:
                raise ValueError(
                    f"{self.slug}: icon_art is the picture for a HUD slot, and "
                    "this perk takes no slot (icon=None)"
                )
            from ..texture.hud_icons import ART

            if self.icon_art not in ART:
                raise ValueError(
                    f"{self.slug}: no HUD art called {self.icon_art!r}; known: "
                    + ", ".join(sorted(ART))
                )
        if not _SLUG.match(self.slug or ""):
            raise ValueError(
                f"{self.slug!r} is not a usable perk slug: it becomes part of "
                "a GSC function name and of a specialty string, so it is "
                "lower case, starts with a letter and holds only a-z, 0-9 "
                "and _"
            )
        if not (self.name or "").strip():
            raise ValueError(f"{self.slug}: a perk needs a name to show the player")
        if '"' in self.name:
            raise ValueError(
                f"{self.slug}: the name goes into the map's .str between "
                "double quotes, so it cannot contain one"
            )
        if int(self.cost) <= 0:
            raise ValueError(
                f"{self.slug}: a perk costs points.  The framework charges "
                "level._custom_perks[perk].cost before it hands over the "
                "bottle (_zm_perks.gsc:612), and a free perk is a machine "
                "every player walks into once"
            )
        if not (self.bottle or "").strip():
            raise ValueError(
                f"{self.slug}: a perk with no bottle takes the player's points "
                "and gives nothing.  _zm_perks.gsc:1825 asserts the argument, "
                ":612 charges before the drink and :617 grants the perk only "
                'on "weapon_change_complete".  Name a stock bottle: '
                + ", ".join(STOCK_BOTTLES)
            )
        if not (self.machine_model or "").strip():
            raise ValueError(
                f"{self.slug}: a perk machine struct with no model is skipped "
                "in silence (_zm_perks.gsc:1419)"
            )
        if not (self.light_fx or "").strip():
            raise ValueError(
                f"{self.slug}: the machine-think loop only starts for a perk "
                "with an alias, a Radiant name and a light effect "
                "(_zm_perks.gsc:98), and until it runs the buy trigger blocks "
                "for ever on a power-on notify nothing sends"
            )
        if not (self.jingle or "").strip() or not (self.sting or "").strip():
            raise ValueError(
                f"{self.slug}: _zm_audio.gsc:1607 reads the use trigger's "
                "script_sound with no isdefined guard, so an unnamed jingle "
                "hands undefined to playsoundwithnotify"
            )

    # -- the names the game knows this perk by ----------------------------
    @property
    def specialty(self) -> str:
        """The string that is the key, the ``script_noteworthy`` and the perk."""
        return f"{SPECIALTY_PREFIX}{self.slug}"

    @property
    def alias(self) -> str:
        """What the power switch notifies on: ``<alias>_on`` (``_zm_power.gsc:695``)."""
        return f"zmf_{self.slug}"

    @property
    def radiant_name(self) -> str:
        """The ``targetname`` the machine-think loop collects machines by."""
        return f"zmf_vending_{self.slug}"

    @property
    def light_handle(self) -> str:
        """This perk's own key into ``level._effect``."""
        return f"zmf_{self.slug}_light"

    @property
    def prefix(self) -> str:
        return f"zmf_perk_{self.slug}"

    @property
    def register_function(self) -> str:
        return f"{self.prefix}_register"

    @property
    def stop_notify(self) -> str:
        """What ends the give thread, which is the framework's own convention."""
        return f"{self.specialty}_stop"

    @property
    def reference(self) -> str:
        """The key this perk's prompt is filed under in the map's ``.str``."""
        return f"PERK_{self.slug.upper()}"


def perk_script(perk: CustomPerk, hint_asset: str) -> CustomScript:
    """The whole server half of ``perk``, as logic on the seam.

    ``hint_asset`` is the linker's name for the prompt in the map's own
    ``.str`` (:func:`zmforge.emit.strings.asset_name`): the map ships the
    string and the script names the asset, and either half alone is a blank
    prompt.

    Everything lands in the map's own ``.gsc``.  There is no second script
    file, no ``scriptparsetree`` line and no client half: a perk's client
    module registers clientfields and machine effects, and this perk registers
    neither -- see :func:`_icon_lines` for why the icon is written rather than
    registered.
    """
    specialty = perk.specialty
    tab = "\t"

    register = CustomFunction(
        name=perk.register_function,
        purpose=(
            f"{perk.name}: a perk of this map's own.\n"
            f"{perk.effect.summary}.\n"
            "The five calls the framework needs, made before the framework "
            "entry because\n"
            "zm_perks::init reads what they wrote (_zm_perks.gsc:40, :172).  "
            "Each call keeps\n"
            "the first registration, so this specialty is ours and no stock "
            "perk can be taken\n"
            "over the same way (_zm_perks.gsc:1903, :1926, :1959, :1987)."
        ),
        body=(
            f'zm_perks::register_perk_basic_info( "{specialty}", "{perk.alias}", '
            f'{int(perk.cost)}, &"{hint_asset}", GetWeapon( "{perk.bottle}" ) );',
            f'zm_perks::register_perk_precache_func( "{specialty}", '
            f"&{perk.prefix}_precache );",
            f'zm_perks::register_perk_machine( "{specialty}", '
            f"&{perk.prefix}_machine );",
            f'zm_perks::register_perk_threads( "{specialty}", &{perk.prefix}_give, '
            f"&{perk.prefix}_take );",
            f'zm_perks::register_perk_host_migration_params( "{specialty}", '
            f'"{perk.radiant_name}", "{perk.light_handle}" );',
        ),
    )

    precache = CustomFunction(
        name=f"{perk.prefix}_precache",
        purpose=(
            "Run by zm_perks::init through default_vending_precaching "
            "(_zm_perks.gsc:172-184).\n"
            "Every name in it is on the stock asset list, so the map declares "
            "no asset for any\n"
            "of them.  off_model and on_model are what the machine-think loop "
            "sets on the\n"
            "machine when the power goes off and on (_zm_perks.gsc:125, :138)."
        ),
        body=(
            f'level._effect[ "{perk.light_handle}" ] = "{perk.light_fx}";',
            f'level.machine_assets[ "{specialty}" ] = SpawnStruct();',
            f'level.machine_assets[ "{specialty}" ].weapon = '
            f'GetWeapon( "{perk.bottle}" );',
            f'level.machine_assets[ "{specialty}" ].off_model = '
            f'"{perk.machine_model}";',
            f'level.machine_assets[ "{specialty}" ].on_model = '
            f'"{perk.machine_model}";',
        ),
    )

    machine = CustomFunction(
        name=f"{perk.prefix}_machine",
        params=("use_trigger", "perk_machine", "bump_trigger", "collision"),
        purpose=(
            "Called on the four entities perk_machine_spawn_init just spawned "
            "(_zm_perks.gsc:\n"
            "register_perk_machine), so the perk stamps its own names on them. "
            " The targetname\n"
            "and the trigger's target are what the machine-think loop collects "
            "by\n"
            "(_zm_perks.gsc:120-122), so they are this perk's Radiant name and "
            "not a stock one.\n"
            "The jingle and the sting are stock alias names and are silent in a "
            "usermap: see\n"
            "the module docstring.  The collision argument is the framework's "
            "shared\n"
            "zm_collision_perks1 model and is left alone."
        ),
        body=(
            f'use_trigger.script_sound = "{perk.jingle}";',
            f'use_trigger.script_label = "{perk.sting}";',
            f'use_trigger.script_string = "{perk.alias}_perk";',
            f'use_trigger.target = "{perk.radiant_name}";',
            f'perk_machine.script_string = "{perk.alias}_perk";',
            f'perk_machine.targetname = "{perk.radiant_name}";',
            *((
                "use_trigger.origin = use_trigger.origin + "
                f"VectorScale( {_front_vector(perk.front_zero)}( perk_machine.angles ), "
                f"{perk.trigger_shift * _front_sign(perk.front_zero):g} );",
            ) if perk.trigger_shift else ()),
            "if ( isdefined( bump_trigger ) )",
            "{",
            f'{tab}bump_trigger.script_string = "{perk.alias}_perk";',
            "}",
        ),
    )

    give_body = [
        '// endon the framework\'s own convention: the take function below sends it',
        f'self endon( "{perk.stop_notify}" );',
        'self endon( "disconnect" );',
    ]
    # The HUD write is its own thread, so a runtime error in it (the path
    # is not a registered clientfield; see _icon_lines) cannot end the give
    # thread before the effect is set up.
    give_body += _icon_thread(perk, 1)
    give_body += list(perk.effect.give)
    give = CustomFunction(
        name=f"{perk.prefix}_give",
        purpose=(
            f"Threaded on the player when {perk.name} is bought "
            "(_zm_perks.gsc:753) and again\n"
            "when it comes back after a pause (:1289).\n"
            f"{perk.effect.summary}."
        ),
        body=tuple(give_body),
    )

    take_body = [f'self notify( "{perk.stop_notify}" );']
    take_body += list(perk.effect.take)
    take_body += _icon_thread(perk, 0)
    take = CustomFunction(
        name=f"{perk.prefix}_take",
        params=("b_pause", "str_perk", "str_result"),
        purpose=(
            "Called on the player when the perk is lost (_zm_perks.gsc:947) and "
            "when it is\n"
            "paused (:1255, which passes b_pause true and nothing else).  The "
            "notify is what\n"
            "ends the give thread above; the framework re-threads it on unpause."
        ),
        body=tuple(take_body),
    )

    using = [r"scripts\zm\_zm_perks", *perk.effect.using]
    if perk.icon is not None:
        using.append(r"scripts\shared\clientfield_shared")
    notes = [
        f"{perk.name} ({specialty}): a perk written in this repository. "
        f"{perk.effect.summary}.",
        *perk.effect.evidence,
    ]
    if perk.icon is not None:
        notes.append(f"icon slot {perk.icon.key}: {perk.icon.evidence}")
    functions = [register, precache, machine, give, take]
    if perk.icon is not None:
        functions.append(CustomFunction(
            name=f"{perk.prefix}_hud",
            params=("n_state",),
            purpose=(
                "Light or clear the perk's HUD slot, in a thread of its own: the "
                "path is not a\nregistered clientfield, and if writing it errors "
                "at run time only this thread\nends, never the perk's effect."
            ),
            body=(
                'self endon( "disconnect" );',
                "wait 0.05;",
                *_icon_lines(perk, "n_state"),
            ),
        ))
    return CustomScript(
        using=tuple(dict.fromkeys(using)),
        functions=tuple(functions),
        statements=((Slot.BEFORE_ENTRY, f"{perk.register_function}();"),),
        notes=tuple(notes),
    )


def _icon_thread(perk: CustomPerk, state: int) -> list[str]:
    """``self thread <prefix>_hud( state );`` when the perk has an icon."""
    if perk.icon is None:
        return []
    return [f"self thread {perk.prefix}_hud( {state} );"]


def _icon_lines(perk: CustomPerk, state) -> list[str]:
    """Write the HUD slot directly, or write nothing.

    Not ``zm_perks::register_perk_clientfields``, and the reason is a failure
    we cannot afford to guess at.  Taking that route would mean registering
    the field on **both** sides, because a clientfield the two sides disagree
    about is a disconnect on join -- and both sides register custom perks by
    walking ``GetArrayKeys( level._custom_perks )`` (``_zm_perks.gsc:
    1631-1643`` and ``_zm_perks.csc:41-52``).  A stock perk is in that array
    from a preload on both sides.  A map's own perk is not: the server half
    can only register in ``main()`` and the client half is a ``REGISTER_SYSTEM``
    preload, so the two sides would fill that array in different orders, and
    whether ``GetArrayKeys`` still hands back the same order either way is
    **not measured**.

    Writing the path costs nothing and risks nothing: ``set_player_uimodel``
    is a direct engine call (``clientfield_shared.gsc:71``
    ``CodeSetUIModelClientField( self, str_field_name, n_value )``) and
    registers no field, so a map with one of these perks registers exactly the
    clientfields it registered without one.  **Whether the shipped widget
    draws an unregistered path is unverified**; the failure if it does not is
    no icon.
    """
    if perk.icon is None:
        return []
    what = {1: "light", 0: "clear"}.get(state, "light or clear")
    return [
        f"// {what} the {perk.icon.key} HUD slot: a key the shipped widget "
        "binds and the",
        "// game ships no art for, so nothing else is drawing in it "
        "(see zmforge.script.perks)",
        f'self clientfield::set_player_uimodel( "{perk.icon.path}", {state} );',
    ]


# --------------------------------------------------------------------------
# The one we wrote
# --------------------------------------------------------------------------
def coin_return(points: int = 100, cost: int = 1500) -> CustomPerk:
    """COIN RETURN: the change machine pays you back at the start of each round.

    Ours, top to bottom.  The name is a vending machine's coin return, the effect is
    :func:`points_each_round`, and both were written here; no published map was
    read for either.  It is deliberately the dullest effect that is still worth
    buying, because the point of the first one is that every part of the chain
    can be checked: the price leaves the score, the drink plays, the icon
    lights, and at the start of the next round the score goes up by a number
    the recipe chose.

    **Unplayed.**  What the tests pin is the text.
    """
    return CustomPerk(
        slug="coin_return",
        name="COIN RETURN",
        cost=int(cost),
        effect=points_each_round(points),
    )


#: The example, at its default price.
COIN_RETURN = coin_return()


def _front_vector(front_zero: Facing) -> str:
    """The GSC angle vector along a machine's front: at yaw 0,
    ``AnglesToRight`` is south (-y) and ``AnglesToForward`` east (+x)."""
    return "AnglesToRight" if front_zero in (Facing.SOUTH, Facing.NORTH) else "AnglesToForward"


def _front_sign(front_zero: Facing) -> float:
    return 1.0 if front_zero in (Facing.SOUTH, Facing.EAST) else -1.0
