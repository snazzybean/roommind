# Time-of-Use Control and Pre-conditioning

RoomMind can read an electricity tariff and shape every room's targets by
time of use: easing demand while energy is expensive, pre-charging while it
is cheap, and coasting through the expensive window on stored heat instead of
bought energy. Everything here builds on the learned thermal model — the
better the model knows your rooms, the better the timing.

Open `Settings -> Energy price` and turn on **Enable Time-of-Use awareness**.
The master switch gates the whole feature: while it is off, rooms behave
exactly as before and the tariff parts of the room cards stay hidden.

## Where the current tier comes from

Pick one answer to **Current tier from** — anything you bind but do not
select is kept, just ignored:

- **Cost sensor** — a numeric price entity (Tibber, Nord Pool, EPEX, aWATTar,
  Octopus, a template, an `input_number`). Set **Cost thresholds** (peak
  from, mid-peak from, ultra-low up to) to map prices onto tiers.
- **Period sensor** — a sensor that *names* the active period. Words like
  `on-peak`, `mid-peak`, `off-peak`, `overnight`/`ultra` are recognized;
  Hydro One's `…_active_peak` states such as `ulo_on_peak` map automatically.
- **Period flags** — for setups where automations toggle one
  `input_boolean`/`binary_sensor` per tier.

When nothing resolves (deleted sensor, unavailable, no thresholds), the tier
is unknown and RoomMind shapes nothing — never guesses.

## How far RoomMind can see into the future

Choose **Plan the tariff future from**. The future view is what enables
pre-conditioning, coasting and the energy price rule rows; **No future view**
means only shaping of the currently active tier:

- **Tariff calendars** (recommended) — bind a `calendar.*` per tier and
  RoomMind gets the *entire* tariff timeline: exact peak windows in both
  directions, which is what the optimizer plans against. The built-in
  **Local Calendar** integration works — no automations required. No
  calendar entities? Define **Manual tariff windows** instead: rows of rate +
  start + end + weekdays, repeating every matching day (an end before the
  start runs past midnight). Rates map to tiers with the same cost
  thresholds.
- **Next-change rate sensor** — for providers that publish *what the price
  will be* after the next change: bind the timestamp, the price, and (if the
  provider labels it) the **Next period name sensor**. The name is read with
  the same word recognition as the current period — no fixed guess needed.
- **Next-change sensor** — for integrations that only say *when* the next
  change starts (e.g. Hydro One's `…_next_peak_starts`). Pair it with **Tier
  after the next change**: for a "next peak starts" sensor pick Peak, which
  always changes into peak. Pick **Not set** to disable the lookahead.
- **No future view** — shaping only.

## Tiers as your source feeds them

`Settings -> Energy price` shows a live dictionary: every tier with the
price your bound sources actually know — observed rate, manual-window rate or
configured threshold, each marked so you can tell them apart — plus the raw
period names that resolve into it, and the strings RoomMind could *not*
place. Assign any unmapped name to a tier right there; the alias outranks
built-in word recognition from the next cycle on, so provider vocabulary the
normalizer cannot read becomes a one-tap fix instead of a helper automation.

The block **pulls, it does not merely recall**: opening it re-reads the cost
sensor, the future sensors and the timeline, so the summary line — *Now:
Off-peak · 8.4 ¢/kWh — Next: Peak at 17:00 · 12.8 ¢/kWh* — reflects your
sources right now. When the future view is incomplete it names the missing
piece (tier, time or price) instead of a bare "no price".

Every valid price is **remembered**: per tier, the last valid cost, a rolling
range and an observation count — including the provider's price for the
upcoming period, kept before that period has ever started. If the cost
entity drops, nothing goes blind: the panel keeps showing the last known
price (marked "(last known)"), `sensor.roommind_energy_rate` reports it, and
a tariff derived from cost thresholds keeps classifying with it for up to an
hour — long enough to ride out a flaky integration, never long enough for a
stale price to steer your heating.

## Room participation

Each room (except outdoor rooms) has two independent switches:

- **Charge cheap, coast expensive** (the room's *Energy price* dialog) — the
  economic layer. RoomMind relaxes targets across future expensive stretches
  and pre-charges cheap hours ahead of them, against the learned decay
  model, so the room coasts on stored heat and lands back on comfort when
  the stretch ends. Presence does not gate the store — the pre-charge often
  runs while the house is empty, which is exactly when energy is cheap.
- **Enable energy price rules for this room** (the *Energy price rules* section on
  the card) — the rules layer (see below). A room without the store can
  still steer purely by rules.

A room with neither switch ignores tariffs entirely. The two switches also
stay hidden while the global master switch is off.

How far the store may shift a target is set by limits — global in
`Settings -> Energy price` under **Fine-tune (optional)**, each optionally
narrowed per room in the same dialog (a blank room field inherits the
global value):

- **Band** (heating/cooling, never below / never above) — the hard consent:
  no target, from any mechanism, ever leaves it.
- **Max deviation (swing)** — how far the store layer may deviate from the
  schedule at all. Relaxation never undercuts the room's eco target.
- **Min price gap** — the ratio expensive-window ÷ cheapest-alternative that
  must be reached before moving is worth it; below it the schedule stands
  untouched.
- **Price-weighted planning** — see next section.

The defaults reproduce familiar Ontario numbers: comfort 21, swing 3, band
17–28 relaxes a peak toward 18 °C and stores up to 24 °C before it. These are
bounds on the room's **indoor target temperature**, not device-output
limits, and separate from the outdoor-temperature gates under Control.

Vacation and manual overrides keep priority: a pre-charge is skipped during
vacation, and a boost you started is never shaved by a tariff. While mold
prevention is active the heating side is not relaxed.

## Price-weighted planning

With a tariff timeline, the MPC weights its energy term by the tier price of
every future block: a run that would burn energy inside the peak costs more,
so the optimizer starts it during the cheap window before the boundary and
lets the learned room model coast through the start of the peak. Turn it off
and the optimizer sees a flat energy price — rules and the store layer still
move targets, but nothing is timed against the tariff.

## Tariff rules (device card)

The *Energy price rules* section steers by tariff **periods** instead of the
clock. Each row is a temporary override of the schedule target, anchored on
a tier boundary, and reads as a sentence:

```
(Peak · starts)  (Override target temperature to)  heating 18 °C, cooling —  (until the next period change)
```

- **Anchor** — which tier's boundary fires the row (`Any period change`
  works too), and whether it is the period **start** or **end**. A rule on
  a period that is *already running* fires immediately — "Peak · starts"
  describes being in peak, not only watching it begin. Optionally restrict
  to weekdays, and to a wall-clock range the boundary itself must fall
  inside.
- **Action** — `Override target temperature to`, `Increase target
  temperature temporarily by`, `Decrease target temperature temporarily by`,
  or `Reach target temperature by time` (see below).
- **Heating / Cooling** — one value per mode, each optional. Each side
  steers a fixed temperature or names the room's own **Comfort** or **Eco**
  target — a named side follows the schedule section when you retune it, so
  rules say "back to comfort" instead of freezing a number. A blank side
  means the row is skipped in that mode (plain tier shaping still applies
  there).
- **End** — until the next period change, for a fixed number of minutes, or
  until a wall-clock time.

Rows carry **priority**: when two rows steer the same side and their windows
overlap, the row listed **lower** on the card wins for the overlap; the
other resumes where the overlap ends. Use the arrows to reorder — the order
lives per room, so reordering never touches the shared rule or another room.

Because the window is part of the MPC horizon, the optimizer decides *when*
to start charging so the room arrives at the hold target by the boundary and
how much of the expensive window it can coast through — the boost hours you
once hard-coded ("02:00 in the loft") become a consequence of the tariff
timeline and the learned room model. During a row window the schedule is
*not* silently abandoned: any schedule target on the wrong side of the row
value is ignored while the window holds, and everything else (manual
override, vacation, windows, mold, compressor protection) keeps its priority.

Cooling mirrors heating: relax the cooling target during the peak and let
the room drift up, or pre-cool in a cheap window.

### Shared rules

A rule is authored once and referenced by every room's row: definitions live
in the shared rule library, rooms keep thin references. Same name always
means the same rule:

- A new rule starts as a **draft on the card** — blank name, nothing sent.
  The name is mandatory: leaving an unnamed rule behind asks whether to
  discard it, and ignoring the question discards it.
- **Editing a rule** from any card updates the single shared definition —
  the card shows "used in N rooms" so the blast radius is visible before you
  type. Edits are staged and reach the server as one save (collapse the row,
  Save, or close the dialog), so the save is atomic.
- **The name field doubles as the rule picker**: choosing another rule's
  name switches the row onto that shared rule (nothing written); typing a
  fresh name renames; renaming a used rule forks a derivative — this room
  keeps the edited rule, the others keep the original.
- **The row enable toggle stays per-room** — one room can park a shared
  rule without switching it off in the others.

A rule is pruned automatically when the last reference disappears —
deleting the row, or deleting the room. Switching a room's schedule (or the
whole tariff feature) off keeps every reference: a temporary measure never
loses rules.

### Reach target temperature by time

The decay-derived action for the classic "heat during the cheap window,
arrive comfortable at the door" case, in two modes:

- **At a time of day** — pick the period that carries the energy under
  *Charge during* and set the clock under *Arrive by*. Ultra-low ends at
  07:00, you leave at 09:00 and the room must be at 20 °C when you go — but
  heating should *stop* at 07:00, not trickle through the morning. RoomMind
  derives the temperature the room must already have at the boundary from
  the learned heat-loss rate:

      needed(t) = outdoor + (20 − outdoor) · e^(α · (09:00 − t))

  A room losing a degree every ten hours against a −2 °C morning needs
  roughly 21.4 °C at 07:00 to coast to exactly 20 °C by 09:00. That derived
  value is the *indirect* 07:00 target — you never schedule it. The MPC
  replans every cycle against the forecast, so the pre-charge lands in the
  cheap window and the schedule series stays continuous at the arrival
  instant.
- **When a period ends** — pick the expensive period under *Coast through*
  and leave the clock empty: the room must land on the target exactly as the
  period ends. Example: pre-charge during mid-peak so the evening peak rides
  down to 19 °C at its end instead of buying heat at peak prices. (Whether a
  pre-charge happens at all is the model's call: on a mild day the passive
  coast already lands high enough and the row demands nothing.)

If the room decays faster than the model predicted, small top-ups are
allowed rather than arriving cold: the temperature at arrival is the
promise, zero energy in between is the best effort. While the thermal model
is still immature the row degrades gracefully to holding the flat target.

### Advanced records through the API

The engine's native record format (`tou_schedules` in settings, written via
the websocket API) exposes what the card does not: a separate lead window
before the boundary, ending on the change *into* a specific tier with a
maximum-hold fallback, the one-way `guard` semantics, and named `comfort` /
`eco` values.

## Other energy sources as tariff tiers

The grid tariff is not the only electricity a room is heated with. Under
`Settings -> Energy price`, **Other energy sources / tiers** promotes a
sensor to a first-class tariff period — a generator burning gas, solar
production, export credit — and the whole dynamic machinery (rules,
pre-conditioning, coasting, price weighting) applies to it unchanged:

- **Holds while** picks how the sensor is read: `Sensor is on` for a binary
  or on/off signal; `Value is above` / `Value is below` for a number
  compared to a threshold — the direction is yours, because meter sign
  conventions differ per integration and RoomMind never guesses; `State is
  one of` for a state name from the sensor's own vocabulary. **For at least**
  debounces chatter (hh:mm:ss plus a milliseconds box — the same idiom as an
  automation trigger's `for:`): a generator reaching steady speed or an inverter
  hovering at standby must not strobe the tariff. While a source holds, its
  boundaries anchor `· starts` / `· ends` rules, and "until the next period
  change" means exactly that: the window closes when the flag drops.
- **Cost per kWh** is typed by you: the gas cost of a kWh for a generator,
  `0` for self-consumed sun, a negative feed-in credit for export. The MPC
  weighs these against the cheapest known grid price — clamped, so free or
  credited energy reads as "as cheap as it gets" instead of a reward to
  chase — so a cheap generator invites pre-conditioning and an expensive one
  invites load-shifting. The grid tariff keeps being tracked underneath and
  resumes the instant the source drops.
- Listed order is priority. A row without a cost still steers rules and the
  panel; it is simply economically neutral.

A few common bindings:

| Source | Bind | Holds while |
|---|---|---|
| Generac / home generator | status sensor (`sensor.generac_status`) | State is one of: `Running`, `Exercising` |
| EcoFlow / Bluetti battery or load | power or SOC sensor (`sensor.home_power_w`) | Value is above a watt (or percent) threshold |
| Victron / Fronius with a **signed** grid meter | grid power sensor | Value is below `0` — a negative grid value means export |
| Shelly EM / PRO 3CT clamp | total power sensor | Value is above a consumption threshold |
| Ripple controller / PV relay | switch or binary sensor | Sensor is on |

Check the sign convention once with your own meter: some integrations report
export as positive and import as negative, and the direction selector is
deliberately yours to set.

## Reading it back

Three global entities reflect the tariff: `sensor.roommind_energy_rate`
(current cost as the sources feed it), `sensor.roommind_energy_period`
(`peak` / `mid` / `off` / `ultra_low`) and `sensor.roommind_energy_next_change`
(the next change the future view can see). They are added once the feature
is enabled. The dashboard's price pill reads the same tier dictionary, the
analytics page keeps its price line and the cheap/expensive heating-hours
breakdown, and diagnostics export the current tier timeline.

## Refresh semantics

The tariff is not polled by a separate timer: every bound source entity is
read fresh once per RoomMind control cycle (about 30 s), and the tier
timeline is rebuilt from scratch in that same cycle. Commands stay
declarative, so a tier change propagates to proportional devices with the
next cycle's setpoints; devices that never report state back (IR) receive a
re-assertion of the last command about every 30 minutes. Nothing about the
tariff path changes how often your devices are commanded overall.

## Example: Hydro One ULO with local calendars

1. Install the Hydro One integration; bind `…_electricity_rate` as the cost
   sensor and `…_active_peak` as the period sensor.
2. Create four Local Calendars (`ULTOU-Peak`, `ULTOU-Mid`, `ULTOU-Low`,
   `ULTOU-UL`) and bind them as tariff calendars with the matching tier.
   The calendars are the schedule of record — RoomMind reads the events; no
   `Power-*` automations or `input_boolean` flags needed.
3. `Settings -> Energy price`: leave the Fine-tune defaults (band 17–28 °C
   heating / 18–30 °C cooling, swing 3 °C, gap ×1) and keep price-weighted
   planning on.
4. Rooms: turn on **Charge cheap, coast expensive** for the loft, kids' and
   dining rooms that should pre-charge overnight and coast through peaks.
   Rooms where peak comfort is non-negotiable simply leave it off.
5. Tariff rule "Evening peak push-out": (Peak · starts) (Override target
   temperature to) heating 18 °C, cooling blank, (until the next period
   change).
6. Tariff rule "Warm for the door": (Reach target temperature by time) (at a
   time of day) (Charge during Ultra-low) heating 20 °C (Arrive by 09:00) —
   RoomMind derives the boundary temperature from the learned decay, so
   heating stops when the cheap window ends and the room is exactly 20 °C
   at departure.

## Example: Hydro One ULO without calendars (sensors only)

The provider's own future sensors are enough — no calendars, no cost
thresholds needed:

- Cost sensor `…_current_all_in_rate`; Period sensor `…_active_peak` (states
  like `ulo_overnight`, recognized by word recognition).
- Future view (**Next-change rate sensor**): timestamp
  `…_next_peak_starts`, price `…_next_peak_all_in_rate`, and the name sensor
  `…_next_peak` in the **Next period name** slot. The tier that follows
  comes from its wording (`ulo_mid_peak` → mid-peak), its price from the
  rate sensor; the dictionary shows *Next: Mid-peak at 07:00 · 0.1766* and
  keeps that value through provider outages.
- Binding the name sensor in the *timestamp* slot still tells you the tier
  and the price — the dictionary then notes the missing clock; move the
  slot to `…_next_peak_starts` to complete the view.
