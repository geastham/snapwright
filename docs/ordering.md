# Getting the bricks

Every build writes three parts lists into `out/`. They're all the same list, in the formats
the big brick marketplaces import:

| file | use it for |
|---|---|
| `<slug>-bricklink.xml` | **ordering on BrickLink** (the biggest marketplace for individual parts) |
| `<slug>-rebrickable.csv` | **checking against what you own** on Rebrickable, and buying through its partner shops |
| `<slug>-parts.csv` | reading and sharing (a spreadsheet): part, colour, quantity, and a **BrickLink link** for each part in its colour |

The 3D viewer has the same list under **Parts**. Click a part to open it on BrickLink, or
download the XML and CSV from there.

Every part-colour combination in these lists has actually been made (it has appeared in
real sets since 2005, according to Rebrickable's set inventories), so you won't be hunting
for a colour that doesn't exist.

## Order on BrickLink (about 5 minutes)

1. Sign in at [bricklink.com](https://www.bricklink.com). It's free.
2. Go to **Want → Upload** and choose **Upload BrickLink XML format**.
3. Open `<slug>-bricklink.xml` in any text editor, copy everything, and paste it into the box.
4. Click **Proceed to verify items**, check the list, choose **Create new Wanted List**
   (name it after your model), and click **Add to Wanted List**.
5. Open the wanted list and click **Buy All**. *Easy Buy* finds the shops that have the most
   of your parts, so you pay the fewest shipping fees.
6. Add to cart shop by shop and check out. Big models usually come from 2-5 shops.

Tips:
- Set the condition to **New** if you want pristine parts, or leave it at *Any* for lower
  prices. The list doesn't set it.
- Order a few spares of the tiny parts (1x1 plates, tiles and round plates). They like to
  vanish.
- Big models can cost more than you'd guess: check the Easy Buy total before you commit. The
  instruction book's cover gives the part count; the viewer's Parts panel gives it colour by
  colour.

([BrickLink's own help on wanted lists](https://www.bricklink.com/help.asp?helpID=207))

## Or with Rebrickable

1. At [rebrickable.com](https://rebrickable.com), open your **Part Lists** (in your
   collection menu), choose **Import**, and upload `<slug>-rebrickable.csv`.
2. Rebrickable shows which parts you already own, if you've added your sets, and what's left
   to buy. **Buy Parts** sends the rest to partner shops.

## Building from what you already have

Have a big tub of bricks? Import the CSV on Rebrickable and add your sets. It tells you which
parts you're missing. Or ask the skill to rebuild the model in fewer colours, or with a
`--no-shapes` build (only bricks, plates and tiles), which uses the most common parts.
