# Brief: snap-in fixture plate for FLF covers (Fusion 360)

You are designing a 3D-printable fixture plate in Fusion 360. Everything you need is below;
you have no other context. Where something is marked OPEN, make it a parameter, use the
stated default, and list it in your answer as a question for the user. Do not invent
answers to OPEN items.

## What the part is for

An FLF cover is a small plastic cover plate for cable outlets (for example an HDMI outlet).
It is designed to snap into a plain rectangular opening in a wall. The user engraves text
on these covers with a Snapmaker Artisan CNC machine (60 degree V-bit, 0.2 mm deep).

The fixture plate imitates that wall: a plate with a rectangular opening that the cover
snaps into, exactly as it would in its final place. The plate is screwed to the machine
table. Because the cover always snaps into the same place, the engraving origin only has
to be set once per fixture, not once per cover.

The fixture holds **one cover**. The holes in the cover (D holes, screw holes) are cut by a
separate program in a separate setup; this fixture does **not** need relief pockets for
them.

## Fixed numbers

| Item | Value |
|---|---|
| Cover outer size | 37.25 mm wide x 62.5 mm long |
| Snap opening (nominal) | 31.2 mm wide (B) x 53.5 mm long (L) |
| Fit clearance on the opening | + 0.2 mm on each dimension (opening becomes 31.4 x 53.7 mm). Make it a parameter. |
| Wall (panel) thickness the clips grip | 4.0 mm. **OPEN:** assumed, not measured. Make it a parameter. |
| Mounting | 4 x M4 screws on a 100 x 100 mm square pattern (hole centres) |
| Manufacturing | 3D print (FDM) |

Orientation: the cover's long side (62.5 mm, opening L = 53.5) runs along the machine's
**Y axis**; the short side (37.25 mm, opening B = 31.2) runs along the machine's **X axis**.
The engraving program uses X = cover width and Y = cover length, so this must hold.

## Geometry to build

1. **Base plate**, about 120 x 120 mm, about 10 mm thick (parameters), corners filleted.
   The 100 x 100 hole pattern is centred on the plate.
2. **Snap opening**: a rectangular through-opening of (B + clearance) x (L + clearance),
   centred on the plate (the centre of the opening = the centre of the screw pattern).
   Small corner radii are fine (FDM cannot print sharp inside corners), but keep them
   small (0.5 mm or less) or add corner relief, so the cover's corners are not pushed out.
3. **Wall thickness at the opening**: around the opening, the material must be exactly the
   panel thickness (default 4 mm), because the clips are made to grip a wall of that
   thickness. Do this with a **relief pocket from the underside**: a pocket larger than the
   opening (default: opening + 6 mm on every side, a parameter), depth = plate thickness
   minus panel thickness. This leaves a 4 mm "wall" around the opening and gives the clips
   room to spring behind it. The underside of the plate sits on the machine table.
4. **Counterbored M4 holes** at the four pattern positions: through hole 4.5 mm,
   counterbore 8.5 mm diameter, 5 mm deep (for DIN 912 socket head screws). The screw heads
   must end **below** the plate's top surface.
5. **Finger notch**: a small recess in the top surface at one short side of the opening
   (about 12 mm wide, 3 mm deep, reaching under the cover's edge) so the cover can be levered
   out with a fingernail or a small screwdriver without touching the engraved face.
6. **Orientation mark**: an embossed or recessed arrow and the word "TOP" next to the
   opening's top short side, plus a small "X+" arrow showing the machine X direction. The
   opening is a plain rectangle, so the cover could be snapped in rotated by 180 degrees;
   the mark tells the user which way round it goes.

## Hard constraints

- **Nothing may stand higher than the cover's top face.** The machine travels only 5 mm
  above the cover between strokes (10 mm at start and end). The plate's top face must be
  at or below the cover's top face once the cover is snapped in, and nothing else
  (no posts, no walls, no text that sticks up more than 0.5 mm) may rise above the plate's
  top face. Screw heads sit in their counterbores.
- The top face must be flat (it defines the cover's height, which defines the engraving depth).
- Use **User Parameters** for every number above, so the user can change the panel
  thickness or the clearance and regenerate.

## What to report back

1. The parametric Fusion 360 design, with the user parameters listed.
2. An STL or 3MF export for printing, and a print orientation that keeps the top face flat
   (for example top face down on the bed, with supports or bridging for the counterbores),
   with suggested settings (PETG or PLA, 0.2 mm layers, at least 4 walls).
3. **The position of the cover's top-left corner** (seen from above, X to the right,
   Y toward the top) relative to the centre of the screw pattern, in mm. The user sets the
   engraving program's origin to this corner. If the cover's outer edge is centred on the
   opening, the corner is at X = -37.25/2 = -18.625 mm, Y = +62.5/2 = +31.25 mm from the
   opening centre. Confirm this or correct it from the model.
4. A suggestion for a quick **test print**: only the 4 mm wall with the snap opening
   (a frame of about 50 x 70 mm), to check the snap fit before printing the whole plate.

## OPEN items to ask the user

- The real wall thickness the clips are made for (4 mm is assumed).
- Where the clips are (all four sides, or only the short sides) and how far they reach
  behind the wall, so the relief pocket is big and deep enough.
- Whether the cover's outer edge is centred on the snap opening (assumed yes).
- Whether the cover flexes under the V-bit. If a test engraving shows uneven depth, a
  support block under the cover may be needed. Do not add it now; only mention it.
- Screw type: socket head (assumed, counterbore) or countersunk (then use a countersink).
