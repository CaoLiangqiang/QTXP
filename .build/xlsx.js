/* 极简 xlsx 写入器：把二维表写成真正的 .xlsx（ZIP + OOXML），不依赖任何库。
   ZIP 压缩方法固定为 0（存储），从而不必内置 deflate；Excel / WPS / Numbers 均可直接打开。
   导出的是真 .xlsx，不是改扩展名的 CSV/HTML，所以不会弹「格式与扩展名不一致」警告。

   用法：miniXlsx(sheetName, rows) -> Uint8Array
   rows: [[cell, ...], ...]
   cell 可以是
     - 字符串 / 数字      普通单元格（数字写成数值型）
     - {v: 值, b: true}   b=true 时该格加粗
     - {n: 数字}          强制数值型
*/
(function (root) {
  'use strict';

  var CRC = (function () {
    var t = new Int32Array(256), i, j, c;
    for (i = 0; i < 256; i++) {
      c = i;
      for (j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[i] = c;
    }
    return t;
  })();

  function crc32(u8) {
    var c = -1, i;
    for (i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ -1) >>> 0;
  }

  function enc(s) { return new root.TextEncoder().encode(s); }

  function concat(parts) {
    var n = 0, i, out, off = 0;
    for (i = 0; i < parts.length; i++) n += parts[i].length;
    out = new Uint8Array(n);
    for (i = 0; i < parts.length; i++) { out.set(parts[i], off); off += parts[i].length; }
    return out;
  }

  /* 只用「存储」方式打包，够 xlsx 用 */
  function zipStore(files) {
    var body = [], dir = [], off = 0;
    files.forEach(function (f) {
      var name = enc(f.name), data = f.data, crc = crc32(data);

      var lf = new Uint8Array(30 + name.length), a = new DataView(lf.buffer);
      a.setUint32(0, 0x04034b50, true);   // 本地文件头签名
      a.setUint16(4, 20, true);           // version needed
      a.setUint16(6, 0x0800, true);       // flag: 文件名为 UTF-8
      a.setUint16(8, 0, true);            // method 0 = stored
      a.setUint16(10, 0, true);           // time
      a.setUint16(12, 0x2821, true);      // date = 2000-01-01（固定，保证输出可复现）
      a.setUint32(14, crc, true);
      a.setUint32(18, data.length, true);
      a.setUint32(22, data.length, true);
      a.setUint16(26, name.length, true);
      a.setUint16(28, 0, true);
      lf.set(name, 30);
      body.push(lf, data);

      var ce = new Uint8Array(46 + name.length), b = new DataView(ce.buffer);
      b.setUint32(0, 0x02014b50, true);   // 中央目录头签名
      b.setUint16(4, 20, true);
      b.setUint16(6, 20, true);
      b.setUint16(8, 0x0800, true);
      b.setUint16(10, 0, true);
      b.setUint16(12, 0, true);
      b.setUint16(14, 0x2821, true);
      b.setUint32(16, crc, true);
      b.setUint32(20, data.length, true);
      b.setUint32(24, data.length, true);
      b.setUint16(28, name.length, true);
      b.setUint16(30, 0, true);
      b.setUint16(32, 0, true);
      b.setUint16(34, 0, true);
      b.setUint16(36, 0, true);
      b.setUint32(38, 0, true);
      b.setUint32(42, off, true);         // 本地头偏移
      ce.set(name, 46);
      dir.push(ce);
      off += lf.length + data.length;
    });

    var cd = concat(dir);
    var end = new Uint8Array(22), e = new DataView(end.buffer);
    e.setUint32(0, 0x06054b50, true);
    e.setUint16(8, files.length, true);
    e.setUint16(10, files.length, true);
    e.setUint32(12, cd.length, true);
    e.setUint32(16, off, true);
    return concat([concat(body), cd, end]);
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function colName(n) {                  // 0 -> A, 25 -> Z, 26 -> AA
    var s = '';
    n += 1;
    while (n > 0) { var r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = (n - r - 1) / 26; }
    return s;
  }

  var XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  var NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  var NSR = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

  function sheetXml(rows) {
    var widths = [], out = [];
    rows.forEach(function (row) {
      row.forEach(function (cell, ci) {
        var v = (cell && typeof cell === 'object') ? (cell.n !== undefined ? cell.n : cell.v) : cell;
        var len = String(v === null || v === undefined ? '' : v).replace(/[^\x00-\xff]/g, '❶❷').length;
        widths[ci] = Math.max(widths[ci] || 8, Math.min(len + 2, 40));
      });
    });

    out.push(XML, '<worksheet xmlns="' + NS + '"><cols>');
    widths.forEach(function (w, i) {
      out.push('<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + w + '" customWidth="1"/>');
    });
    out.push('</cols><sheetData>');

    rows.forEach(function (row, ri) {
      out.push('<row r="' + (ri + 1) + '">');
      row.forEach(function (cell, ci) {
        var ref = colName(ci) + (ri + 1), bold = false, v;
        if (cell && typeof cell === 'object') {
          bold = !!cell.b;
          v = cell.n !== undefined ? cell.n : cell.v;
        } else v = cell;
        if (v === null || v === undefined || v === '') return;
        var s = bold ? ' s="1"' : '';
        var isNum = (typeof v === 'number' && isFinite(v)) ||
                    (cell && typeof cell === 'object' && cell.n !== undefined);
        if (isNum) out.push('<c r="' + ref + '"' + s + '><v>' + v + '</v></c>');
        else out.push('<c r="' + ref + '"' + s + ' t="inlineStr"><is><t>' + esc(v) + '</t></is></c>');
      });
      out.push('</row>');
    });
    out.push('</sheetData></worksheet>');
    return out.join('');
  }

  function miniXlsx(sheetName, rows) {
    var name = String(sheetName || 'Sheet1').replace(/[\\\/\?\*\[\]:]/g, '_').slice(0, 31);
    var files = [
      { name: '[Content_Types].xml', data: enc(XML +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
        '</Types>') },
      { name: '_rels/.rels', data: enc(XML +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="' + NSR + '/officeDocument" Target="xl/workbook.xml"/>' +
        '</Relationships>') },
      { name: 'xl/workbook.xml', data: enc(XML +
        '<workbook xmlns="' + NS + '" xmlns:r="' + NSR + '"><sheets>' +
        '<sheet name="' + esc(name) + '" sheetId="1" r:id="rId1"/></sheets></workbook>') },
      { name: 'xl/_rels/workbook.xml.rels', data: enc(XML +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="' + NSR + '/worksheet" Target="worksheets/sheet1.xml"/>' +
        '<Relationship Id="rId2" Type="' + NSR + '/styles" Target="styles.xml"/>' +
        '</Relationships>') },
      { name: 'xl/styles.xml', data: enc(XML +
        '<styleSheet xmlns="' + NS + '">' +
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>' +
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>' +
        '<fills count="2"><fill><patternFill patternType="none"/></fill>' +
        '<fill><patternFill patternType="gray125"/></fill></fills>' +
        '<borders count="1"><border/></borders>' +
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>' +
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>' +
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
        '</styleSheet>') },
      { name: 'xl/worksheets/sheet1.xml', data: enc(sheetXml(rows)) }
    ];
    return zipStore(files);
  }

  root.miniXlsx = miniXlsx;
  if (typeof module !== 'undefined' && module.exports) module.exports = miniXlsx;
})(typeof globalThis !== 'undefined' ? globalThis : this);
