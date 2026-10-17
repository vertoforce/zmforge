"""The map script as a model, not as text.

Spec section 5.3 is emphatic that the script must be *regenerated* from a
model every commit rather than patched around textual anchors, so this is the
whole of what the generated ``.gsc``/``.csc`` say, in structured form.  The
zone hook's function name is free; ``connect_zones`` is this design's choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..script.custom import CustomScript

__all__ = ["ZoneEdge", "ScriptEntry", "ScriptPlan"]


@dataclass(frozen=True, slots=True)
class ZoneEdge:
    """One ``add_adjacent_zone`` call: two zones joined by a door flag."""

    zone_a: str
    zone_b: str
    flag: str


@dataclass(frozen=True, slots=True)
class ScriptEntry:
    """A zone the map's own script puts players into, not a door.

    A sealed start room each player spawns in, or a room a script teleports
    players to, is entered without any ``add_adjacent_zone`` edge and without
    any floor joining it to the spawn.  Declaring it here is how the checks
    that flood the map from the spawn (Z3's door-graph walk, Z25's walk on
    foot) count it as entered instead of reporting it unreachable: the zone
    seeds the door walk and every point seeds the foot flood, exactly as an
    initial-spawn slot does.  ``why`` says which mechanic does the entering.
    """

    zone: str
    points: tuple[tuple[float, float, float], ...]
    why: str


@dataclass
class ScriptPlan:
    """Everything the generated scripts need to know."""

    map_name: str
    zone_hook: str = "connect_zones"
    dog_rounds: bool = False
    zones: list[str] = field(default_factory=list)
    edges: list[ZoneEdge] = field(default_factory=list)
    perk_modules: list[str] = field(default_factory=list)
    chest_name: str | None = None
    #: True once a Der Wunderfizz is placed.  It buys both scripts a
    #: ``#using`` of :data:`~zmforge.blueprint.catalogue.WUNDERFIZZ_MODULE`
    #: and the server script the rotation calls below; false emits exactly
    #: the pair of scripts that were emitted before the machine existed.
    wunderfizz: bool = False
    #: Every ``specialty_`` string a perk placed on this map registers, in
    #: the order the perks were placed.  :meth:`Blueprint.place_perk` fills
    #: it in whether or not a Wunderfizz is ever placed, so the two calls are
    #: order-independent.
    perk_rotation: list[str] = field(default_factory=list)
    #: A rotation the recipe named itself, which replaces the one above.
    #: ``None`` -- the default -- means "the perks on the map".
    #:
    #: Both lists are ``specialty_`` strings and both are constrained the
    #: same way: ``zm_perk_random.gsc:725-733 get_perk_weapon_model`` reads
    #: ``level.machine_assets[ perk ].weapon`` for whatever it is about to
    #: hand over, and that array is only ever written by a perk *module*
    #: (``_zm_perk_juggernaut.gsc:72``).  So a perk in the rotation whose
    #: module the map does not ``#using`` is a perk the machine cannot
    #: render.  Check Z49 refuses that pair.
    wunderfizz_rotation: list[str] | None = None
    #: Effects the map declares, which both scripts must precache by name.
    #: An ``fx`` asset in the manifest is packed into the fastfile and is
    #: still nothing the game will play: the handle comes from the
    #: ``#precache`` directive, and the client script's copy of it is spelled
    #: ``client_fx`` (``zm_giant.gsc:62-68`` against ``zm_giant_fx.csc:9-28``
    #: in the mod tools' own raw scripts).  :meth:`Blueprint.declare_asset`
    #: fills this in, so declaring the asset is all a caller does.
    precache_fx: list[str] = field(default_factory=list)
    always_on_flag: str = "always_on"
    repeat_game_mode: bool = False
    #: Turn the framework's own player-count check off, which is the one
    #: thing about seating more than four players a *map* can do for itself.
    #: ``_zm.gsc:7067 player_too_many_players_check()`` sets ``max_players =
    #: 4`` (8 only for ``zgrief``/``zmeat``) and, above that, calls
    #: ``zm_game_module::freeze_players(true)`` and ``level notify(
    #: "end_game" )``; ``_zm.gsc:1865`` threads it from ``onPlayerSpawned``
    #: on every spawn, so the fifth player to join ends the match.  The gate
    #: is ``level.player_too_many_players_check``, assigned ``true`` at
    #: ``_zm.gsc:252`` inside ``zm::init()``, which the framework entry
    #: reaches synchronously (``zm_usermap::main()`` -> ``load::main()``
    #: (``_load.gsc:79``) -> ``zm::init()``), so an assignment after the
    #: entry lands between the write and the read.  Nothing else in the mod
    #: tools' raw scripts assigns that variable.  :meth:`Blueprint.
    #: set_player_start` sets this whenever ``slots`` exceeds
    #: :data:`~zmforge.blueprint.elements.STOCK_PLAYER_SLOTS`; check Z26
    #: fails a written map that has the structs and not the statement.
    lift_player_cap: bool = False
    #: How many players the map is being built to seat, which is
    #: :attr:`~zmforge.blueprint.elements.PlayerStart.slots`.  Four is a
    #: stock game and changes nothing about the emitted scripts; above four
    #: it is the loop bound of every per-player registration the stock
    #: scripts only did four of, so the number lives here once instead of
    #: being written out at each of them.
    player_slots: int = 4
    #: The map's own weapon table, as the zone line and both
    #: ``load_weapon_spec_from_table`` calls spell it, or ``None`` for a map
    #: that ships none.  ``None`` is the default and emits exactly the pair of
    #: scripts that were emitted before custom prices existed:
    #: :meth:`Blueprint.place_wall_weapon` sets it only when a price or a
    #: custom weapon asks for it.  Set, it costs three things in the emitted
    #: text, and all three are load-bearing -- the assignment of
    #: ``level._zombie_custom_add_weapons`` *before* the framework entry, the
    #: loader function it points at, and the client script's own load *after*
    #: the framework entry, because the price on the prompt is filled in
    #: client side and ``zm_usermap.csc:83`` has no hook.
    weapon_table: str | None = None
    #: ``(weapon, localized string asset)`` for every wall buy whose prompt
    #: this map renames.  Empty is the default and emits exactly the script
    #: that was emitted before renamed prompts existed.
    #:
    #: The framework does not read a name from anywhere a map can write to:
    #: ``add_zombie_weapon`` ignores the table's ``hint`` column and assigns
    #: ``&"ZOMBIE_WEAPONCOSTONLYFILL"`` itself (``_zm_weapons.gsc:559-566``).
    #: What it does read, every time it builds or resets a wall buy's
    #: unitrigger, is ``level.zombie_weapons[weapon].hint`` through
    #: ``get_weapon_hint()`` (``_zm_weapons.gsc:1417-1422``, used at ``:969``
    #: and ``:1305``).  So each pair becomes one assignment over that field,
    #: emitted inside the table loader -- after the tables are loaded, which
    #: is what writes the framework's own reference, and before the stubs are
    #: built, which is what reads it.  There is no other window, and it is
    #: not a slot a caller can reach.
    #:
    #: The asset on the right is the linker's own name for a reference in the
    #: map's ``.str`` (:func:`zmforge.emit.strings.asset_name`), so setting
    #: this without shipping the file leaves the prompt blank in game.
    #: :meth:`Blueprint.rename_weapon_prompt` fills both in together.
    weapon_hints: list[tuple[str, str]] = field(default_factory=list)
    #: The localized-string asset behind every custom perk's buy prompt, in
    #: declaration order.  Empty is the default and emits exactly the script
    #: that was emitted before a map could ship a perk of its own.
    #:
    #: It is a ``#precache( "string", ... )`` line and nothing else: the
    #: reference itself is handed to ``zm_perks::register_perk_basic_info``
    #: by the perk's own registration function, and the framework passes it
    #: to ``SetHintString( hint, cost )`` (``_zm_perks.gsc:395``, ``:530``).
    #: The directive is what gives the script a handle for it, which is the
    #: same rule an effect lives under -- and it is the spelling every stock
    #: perk module uses (``_zm_perk_juggernaut.gsc:29``
    #: ``#precache( "string", "ZOMBIE_PERK_JUGGERNAUT" );``).
    perk_hints: list[str] = field(default_factory=list)
    #: The map's own words that a custom script shows, as ``(kind, asset)``:
    #: ``triggerstring`` for a prompt set on a script-spawned trigger and
    #: ``string`` for a line printed to a player.  Filled by
    #: :meth:`~zmforge.blueprint.model.Blueprint.add_map_string`.
    map_strings: list[tuple[str, str]] = field(default_factory=list)
    #: Gameplay logic a caller supplied, woven in at emission
    #: (:mod:`zmforge.script`).  Empty by default: a map that asks for no
    #: custom logic emits exactly the script it always emitted.
    custom: CustomScript = field(default_factory=CustomScript)
    #: Zones the custom logic puts players into without a door or a floor
    #: (:class:`ScriptEntry`).  Empty by default, which changes no check.
    entries: list[ScriptEntry] = field(default_factory=list)

    def rotation(self) -> list[str]:
        """The perks the Wunderfizz offers, de-duplicated, in order.

        A recipe's own list wins outright; otherwise it is the perks the map
        places.  Empty is a real answer and a broken machine, which is why
        it is a check and not an assertion: see Z49.
        """
        source = (
            self.wunderfizz_rotation
            if self.wunderfizz_rotation is not None
            else self.perk_rotation
        )
        seen: set[str] = set()
        ordered: list[str] = []
        for specialty in source:
            if specialty not in seen:
                seen.add(specialty)
                ordered.append(specialty)
        return ordered

    def module_set(self) -> list[str]:
        """Perk modules, de-duplicated, in first-placed order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for module in self.perk_modules:
            if module not in seen:
                seen.add(module)
                ordered.append(module)
        return ordered
