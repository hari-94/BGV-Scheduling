/**
 * ENG sheet update -- Office Script for "Daily Tasks Ops Departments.xlsx",
 * tab "RQS-ENG-Runners" (renamed "Runner Report " on 19 Nov; found by its
 * layout when the name doesn't match). Run by the Power Automate flow "BGV ENG sheet" with
 * the text file the office PC drops into "App Outbox" after a Push
 * (eng_sheet.py builds it).
 *
 * Writes ONLY: the date/time at the top (B2), the AM houseperson names
 * (column E, rows of the "AM Housepersons" block, by HSP number and the
 * "Hsp Lead Am" row), the PM houseperson names (column E, from "PM
 * Housepersons" down to "Front Desk", by HSP number and the "HSP Lead PM"
 * row), and the RQS names + Full Clean rooms (columns F and G)
 * under the BLD 1 / BLD 2 / BLD 3 labels. Everything else belongs to other
 * teams and is not touched. Rows are found by their labels, not fixed row
 * numbers, so a row added to the sheet doesn't send names to the wrong place.
 */
function main(workbook: ExcelScript.Workbook, payload: string) {
  const p = JSON.parse(payload) as {
    title: string;
    housepersons: { [slot: string]: string[] };
    housepersons_pm?: { [slot: string]: string[] };
    rqs: { [bld: string]: string[][] };
    repair_only?: boolean;
    title_only?: boolean;
  };

  // One-off repair (22 Nov 2026). The find() below used to return the FIRST
  // tab, so three runs wrote this script's title over the front desk's own
  // heading in "FD Daily Task List" B2. Put it back as it was -- only while
  // the cell still holds one of our "11/22/2026 · Updated ..." lines.
  try {
    const fd = workbook.getWorksheet("FD Daily Task List");
    const h = fd ? fd.getRange("B2") : undefined;
    if (h && /^\d{1,2}\/\d{1,2}\/\d{4}\s+\S\s+Updated /.test(String(h.getValue()))) {
      h.setValue("GC8 Front Desk Daily Tasks");
      const hf = h.getFormat();
      const font = hf.getFont();
      font.setName("Book Antiqua");
      font.setSize(18);
      font.setBold(true);
      font.setColor("#000000");
      hf.setHorizontalAlignment(ExcelScript.HorizontalAlignment.center);
      hf.setVerticalAlignment(ExcelScript.VerticalAlignment.center);
      hf.setWrapText(false);
      console.log("Front desk heading in 'FD Daily Task List' B2 put back");
    }
  } catch (e) { console.log("Front desk heading not checked: " + e); }

  // The tab is found by its layout when its name has changed: on 19 Nov it was
  // renamed "Runner Report " and the next run failed on the old name.
  const isOurs = (w: ExcelScript.Worksheet) => {
    try {
      const v = w.getRange("A1:K20").getValues();
      const has = (c: number, re: RegExp) => v.some(row => re.test(String(row[c] ?? "").trim()));
      return has(1, /^am housepersons/i) && has(5, /^housekeeping rqs/i);
    } catch (e) { return false; }
  };
  // A plain loop, never getWorksheets().find(isOurs): Office Scripts runs any
  // function that calls Excel asynchronously, so find() got a Promise back --
  // always truthy -- and returned the first tab, "FD Daily Task List"
  // (21-22 Nov). Array callbacks must not call Excel when their result matters.
  let ws = workbook.getWorksheet("RQS-ENG-Runners");
  if (!ws) {
    for (const w of workbook.getWorksheets()) {
      if (isOurs(w)) {
        ws = w;
        break;
      }
    }
  }
  if (!ws) throw new Error("No tab with 'AM Housepersons' in column B and 'Housekeeping RQS' in column F");

  // One text style for every cell this script writes (HP, 4 Nov): the cells
  // had kept whatever font, size, colour and bold someone once gave them, so
  // the names looked uneven. The font and size are the workbook's own Normal
  // style -- its body text -- so they match the rest of the tab. Fill and
  // borders belong to the sheet's design and are left alone.
  // A cell nobody has touched carries the workbook's Normal style.
  let fontName = "Calibri";
  let fontSize = 11;
  try {
    const plain = ws.getRange("Z200").getFormat().getFont();
    fontName = plain.getName() || fontName;
    fontSize = plain.getSize() || fontSize;
  } catch (e) { /* keep Calibri 11 */ }
  // Never lets a formatting hiccup stop the names being written.
  const even = (r: ExcelScript.Range, bold = false) => {
    try {
      const f = r.getFormat();
      const font = f.getFont();
      font.setName(fontName);
      font.setSize(fontSize);
      font.setColor("#000000");
      font.setBold(bold);
      font.setItalic(false);
      font.setUnderline(ExcelScript.RangeUnderlineStyle.none);
      font.setStrikethrough(false);
      f.setHorizontalAlignment(ExcelScript.HorizontalAlignment.left);
      f.setVerticalAlignment(ExcelScript.VerticalAlignment.center);
      f.setWrapText(true);
    } catch (e) { /* the value is written; only the look is skipped */ }
  };

  const vals = ws.getRange("A1:K80").getValues();
  const cell = (r: number, c: number) => String(vals[r][c] ?? "").trim();   // r, c are 0-based
  const B = 1, C = 2, D = 3, E = 4, F = 5, G = 6;
  const find = (col: number, test: (s: string) => boolean, from = 0) => {
    for (let r = from; r < vals.length; r++) if (test(cell(r, col))) return r;
    return -1;
  };

  // Nothing is written unless this tab really is the Runner Report, checked on
  // this tab's own cells -- so a wrong pick can't reach another team's tab.
  if (find(B, s => /^am housepersons/i.test(s)) < 0 || find(F, s => /^housekeeping rqs/i.test(s)) < 0) {
    throw new Error(`Tab '${ws.getName()}' has no 'AM Housepersons' (B) and 'Housekeeping RQS' (F) -- nothing written`);
  }
  console.log(`Runner Report tab: '${ws.getName()}'`);
  if (p.repair_only) return;     // a repair run: the heading above, and this check

  // 1. date and time at the top: the title bar, centred, bold and bigger than
  // the names below (Hari, 22 Nov). B2 is the corner of the merged B2:J3, so
  // centring it centres the text across the bar.
  const top = ws.getRange("B2");
  top.setValue(p.title);
  try {
    const tf = top.getFormat();
    const tfont = tf.getFont();
    tfont.setName(fontName);
    tfont.setSize(16);
    tfont.setBold(true);
    tfont.setColor("#000000");
    tfont.setItalic(false);
    tf.setHorizontalAlignment(ExcelScript.HorizontalAlignment.center);
    tf.setVerticalAlignment(ExcelScript.VerticalAlignment.center);
    tf.setWrapText(false);
  } catch (e) { /* the title is written; only its look is skipped */ }
  console.log(`Title: ${p.title}`);
  if (p.title_only) return;      // the names were typed by hand that day: leave them

  // 2. AM housepersons: between "AM Housepersons" and "PM Housepersons"
  const am = find(B, s => /^am housepersons/i.test(s));
  const pm = find(B, s => /^pm housepersons/i.test(s), am + 1);
  if (am >= 0 && pm > am) {
    for (let r = am + 1; r < pm; r++) {
      const m = cell(r, D).match(/^hsp\s*(\d)/i);
      let slot = m ? `HSP ${m[1]}` : "";
      if (!slot && /hsp lead am/i.test(cell(r, C))) slot = "LEAD";
      if (slot && p.housepersons[slot] !== undefined) {
        ws.getCell(r, E).setValue(p.housepersons[slot].join(" / "));
        even(ws.getCell(r, E));
      }
    }
  }

  // 2b. PM housepersons: from "PM Housepersons" down to "Front Desk". Column B
  // doesn't end the block: its HSP rows sit beside "BLD 1".."BLD 3", and its
  // "HSP Lead PM" row is under "Overnight" (28 Oct). Each slot is written
  // once, on the first row after the heading that names it, so nothing
  // further down can be reached. A payload from before the PM names were
  // sent has none, and leaves the block alone.
  const pmNames = p.housepersons_pm;
  if (pm >= 0 && pmNames) {
    let stop = find(B, s => /^front desk/i.test(s), pm + 1);
    if (stop < 0) stop = vals.length;
    const done: { [slot: string]: boolean } = {};
    for (let r = pm + 1; r < stop; r++) {
      const m = cell(r, D).match(/^hsp\s*(\d)/i);
      let slot = m ? `HSP ${m[1]}` : "";
      if (!slot && /hsp\s*lead\s*pm/i.test(cell(r, C))) slot = "LEAD";
      if (slot && !done[slot] && pmNames[slot] !== undefined) {
        ws.getCell(r, E).setValue(pmNames[slot].join(" / "));
        even(ws.getCell(r, E));
        done[slot] = true;
      }
    }
  }

  // 3. RQS and rooms under each building label in column G
  const head = find(F, s => /^housekeeping rqs/i.test(s));
  let end = find(B, s => /^front desk/i.test(s), head + 1);
  if (end < 0) end = vals.length;
  const labels: { row: number; bld: string }[] = [];
  for (let r = head + 1; r < end; r++) {
    const m = cell(r, G).match(/^bld\s*(\d)$/i);
    if (m) labels.push({ row: r, bld: m[1] });
  }
  labels.forEach((lab, i) => {
    const first = lab.row + 1;
    const last = (i + 1 < labels.length ? labels[i + 1].row : end) - 1;
    const rows = last - first + 1;
    if (rows <= 0) return;
    const entries = (p.rqs[lab.bld] || []).map(e => [e[0], e[1]]);
    if (entries.length > rows) {            // more RQS than rows: the rest share the last row
      const extra = entries.splice(rows - 1);
      entries.push([extra.map(e => e[0]).join(" / "), extra.map(e => `${e[0]}: ${e[1]}`).join("   ")]);
    }
    for (let k = 0; k < rows; k++) {
      ws.getCell(first + k, F).setValue(k < entries.length ? entries[k][0] : "");
      ws.getCell(first + k, G).setValue(k < entries.length ? entries[k][1] : "");
      even(ws.getRangeByIndexes(first + k, F, 1, 2));
    }
  });
}
