// Webcam still -> Pebble 4-bit palettized image (drawn by src/c/cam.c).
// Centre-crop and area-average to w x h, pick 16 of the 64 Pebble colours, Floyd-Steinberg dither,
// pack two pixels per byte (left pixel in the high nibble).
var decodeJpeg = require('./vendor/jpeg-decoder');

var LEVEL = [0, 85, 170, 255];
var MAX_SAMPLES = 8;  // per axis per output pixel; enough for an average, keeps huge images fast

// Some cameras (the FGC ones) leave zero bytes between header segments. Browsers skip them
// ("extraneous bytes before marker"); jpeg-js stops, so cut them out before decoding.
function dropPadding(bytes) {
  var parts = [];
  var start = 0;
  var i = 2;  // after SOI
  while (i + 3 < bytes.length) {
    if (bytes[i] !== 0xFF) {
      var j = i;
      while (j < bytes.length && bytes[j] !== 0xFF) {
        j++;
      }
      parts.push(bytes.subarray(start, i));
      start = i = j;
      continue;
    }
    var marker = bytes[i + 1];
    if (marker === 0xDA || marker === 0xD9) {
      break;  // start of scan: the entropy-coded data follows, leave it alone
    }
    if (marker === 0xFF) {
      i++;  // fill byte before a marker
      continue;
    }
    i += 2 + ((bytes[i + 2] << 8) | bytes[i + 3]);
  }
  if (!parts.length) {
    return bytes;
  }
  parts.push(bytes.subarray(start));
  var total = 0;
  parts.forEach(function (p) { total += p.length; });
  var out = new Uint8Array(total);
  var o = 0;
  parts.forEach(function (p) {
    out.set(p, o);
    o += p.length;
  });
  return out;
}

function bin(r, g, b) {  // index of the nearest Pebble colour, 0brrggbb
  return (Math.round(r / 85) << 4) | (Math.round(g / 85) << 2) | Math.round(b / 85);
}

function downscale(rgba, sw, sh, w, h) {
  var scale = Math.min(sw / w, sh / h);
  var x0 = (sw - w * scale) / 2;
  var y0 = (sh - h * scale) / 2;
  var out = new Float32Array(w * h * 3);
  for (var y = 0; y < h; y++) {
    var ya = Math.floor(y0 + y * scale);
    var yb = Math.max(ya + 1, Math.floor(y0 + (y + 1) * scale));
    var ys = Math.max(1, Math.floor((yb - ya) / MAX_SAMPLES));
    for (var x = 0; x < w; x++) {
      var xa = Math.floor(x0 + x * scale);
      var xb = Math.max(xa + 1, Math.floor(x0 + (x + 1) * scale));
      var xs = Math.max(1, Math.floor((xb - xa) / MAX_SAMPLES));
      var r = 0, g = 0, b = 0, n = 0;
      for (var yy = ya; yy < yb; yy += ys) {
        for (var xx = xa; xx < xb; xx += xs) {
          var i = (yy * sw + xx) * 4;
          r += rgba[i];
          g += rgba[i + 1];
          b += rgba[i + 2];
          n++;
        }
      }
      var o = (y * w + x) * 3;
      out[o] = r / n;
      out[o + 1] = g / n;
      out[o + 2] = b / n;
    }
  }
  return out;
}

// Greedy pick: weigh each colour's pixel count by its distance to the colours already chosen,
// so a small patch of blue sky still gets a colour next to the large whites and greys.
function choosePalette(img, size) {
  var counts = [];
  for (var c = 0; c < 64; c++) {
    counts.push(0);
  }
  for (var i = 0; i < img.length; i += 3) {
    counts[bin(img[i], img[i + 1], img[i + 2])]++;
  }
  var chosen = [];
  while (chosen.length < size) {
    var best = -1;
    var bestScore = 0;
    for (var cand = 0; cand < 64; cand++) {
      if (!counts[cand] || chosen.indexOf(cand) >= 0) {
        continue;
      }
      var dist = chosen.length ? 1e9 : 1;
      chosen.forEach(function (p) {
        var dr = (cand >> 4) - (p >> 4);
        var dg = ((cand >> 2) & 3) - ((p >> 2) & 3);
        var db = (cand & 3) - (p & 3);
        dist = Math.min(dist, dr * dr + dg * dg + db * db);
      });
      if (counts[cand] * dist > bestScore) {
        bestScore = counts[cand] * dist;
        best = cand;
      }
    }
    if (best < 0) {
      break;
    }
    chosen.push(best);
  }
  return chosen;
}

function dither(img, w, h, palette) {
  var rgb = palette.map(function (c) { return [LEVEL[c >> 4], LEVEL[(c >> 2) & 3], LEVEL[c & 3]]; });
  var idx = new Uint8Array(w * h);
  function spread(x, y, er, eg, eb, f) {
    if (x < 0 || x >= w || y >= h) {
      return;
    }
    var o = (y * w + x) * 3;
    img[o] += er * f;
    img[o + 1] += eg * f;
    img[o + 2] += eb * f;
  }
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var o = (y * w + x) * 3;
      var r = img[o], g = img[o + 1], b = img[o + 2];
      var best = 0;
      var bestD = 1e12;
      for (var p = 0; p < rgb.length; p++) {
        var dr = r - rgb[p][0], dg = g - rgb[p][1], db = b - rgb[p][2];
        var d = dr * dr + dg * dg + db * db;
        if (d < bestD) {
          bestD = d;
          best = p;
        }
      }
      idx[y * w + x] = best;
      var er = r - rgb[best][0], eg = g - rgb[best][1], eb = b - rgb[best][2];
      spread(x + 1, y, er, eg, eb, 7 / 16);
      spread(x - 1, y + 1, er, eg, eb, 3 / 16);
      spread(x, y + 1, er, eg, eb, 5 / 16);
      spread(x + 1, y + 1, er, eg, eb, 1 / 16);
    }
  }
  return idx;
}

function pack(idx, w, h) {
  var stride = Math.ceil(w / 2);
  var out = new Uint8Array(stride * h);
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      var v = idx[y * w + x];
      out[y * stride + (x >> 1)] |= (x & 1) ? v : v << 4;
    }
  }
  return out;
}

// jpeg: ArrayBuffer or Uint8Array of a JPEG file. Returns {width, height, palette: [GColor8],
// data: Uint8Array (4 bpp rows of ceil(width / 2) bytes), indices: Uint8Array}
function convert(jpeg, width, height) {
  var raw = decodeJpeg(dropPadding(new Uint8Array(jpeg)),
                       { useTArray: true, formatAsRGBA: true, maxResolutionInMP: 40 });
  var img = downscale(raw.data, raw.width, raw.height, width, height);
  var palette = choosePalette(img, 16);
  var idx = dither(img, width, height, palette);
  return {
    width: width,
    height: height,
    palette: palette.map(function (c) { return 0xC0 | c; }),
    data: pack(idx, width, height),
    indices: idx
  };
}

module.exports = { convert: convert, LEVEL: LEVEL };
