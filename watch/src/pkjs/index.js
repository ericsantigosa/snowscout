// Snowscout phone side: fetch data.json from GitHub Pages, pack it into one byte blob for the
// watch, run the Clay settings page (favourites, hidden resorts, first board), and fetch and
// convert webcam stills on request.
var Clay = require('pebble-clay');
var buildConfig = require('./config');
var cam = require('./cam');

var DATA_URL = 'https://ericsantigosa.github.io/snowscout/data.json';

// Wire format of one resort; must match REC_SIZE and the offsets in src/c/data.c
var REC_SIZE = 50;
var NAME_BYTES = 16;
var NO_DATA = -32768;
var REGION = { CAT: 0, AND: 1, FR: 2 };
var FLAG_CAM = 0x40;
var FLAG_FAV = 0x80;

// Webcam image size and transfer chunk; must fit CAM_W/CAM_H and the inbox in src/c/main.c
var CAM_W = 200;
var CAM_H = 120;
var CAM_CHUNK = 2000;

var sentRows = [];  // resorts in the order last sent to the watch; CAM_REQ indexes into it
var camRequest = 0; // id of the newest webcam request; older ones stop sending

// Clay only registers the components used by the config it is constructed with, so build it
// with a one-resort config (every component type); the real list is set in showConfiguration.
var clay = new Clay(buildConfig([{ id: '', n: '', reg: '' }]), null, { autoHandleEvents: false });

function loadJSON(key, fallback) {
  try {
    var value = JSON.parse(localStorage.getItem(key));
    return value === null ? fallback : value;
  } catch (e) {
    return fallback;
  }
}

// favourites and hidden resorts are kept by resort id, so they survive changes to the list
function prefs() {
  var p = loadJSON('snowscout-prefs', {});
  return { board: p.board || 0, fav: p.fav || [], hide: p.hide || [] };
}

function utf8(str) {
  var encoded = unescape(encodeURIComponent(str));
  var bytes = [];
  for (var i = 0; i < encoded.length; i++) {
    bytes.push(encoded.charCodeAt(i));
  }
  return bytes;
}

// UTF-8 name cut to NAME_BYTES without splitting a character
function nameBytes(name) {
  var out = [];
  for (var i = 0; i < name.length; i++) {
    var b = utf8(name.charAt(i));
    if (out.length + b.length > NAME_BYTES) {
      break;
    }
    out = out.concat(b);
  }
  return out;
}

function put16(buf, offset, value) {
  if (value === null || value === undefined) {
    value = NO_DATA;
  }
  value = value & 0xFFFF;
  buf[offset] = value & 0xFF;
  buf[offset + 1] = value >> 8;
}

function pack(data, p) {
  var rows = data.r.filter(function (r) { return p.hide.indexOf(r.id) < 0; });
  var buf = [];
  rows.forEach(function (r) {
    var off = buf.length;
    for (var i = 0; i < REC_SIZE; i++) {
      buf.push(0);
    }
    var name = nameBytes(r.n);
    for (var j = 0; j < name.length; j++) {
      buf[off + j] = name[j];
    }
    buf[off + 16] = (REGION[r.reg] || 0) | (r.cam ? FLAG_CAM : 0) | (p.fav.indexOf(r.id) >= 0 ? FLAG_FAV : 0);
    buf[off + 17] = (r.tmin === null || r.tmin === undefined) ? 0x80 : (r.tmin & 0xFF);
    put16(buf, off + 18, r.alt);
    put16(buf, off + 20, r.drv);
    put16(buf, off + 22, r.f48);
    put16(buf, off + 24, r.c72);
    put16(buf, off + 26, r.lo);
    put16(buf, off + 28, r.hi);
    put16(buf, off + 30, r.m24);
    put16(buf, off + 32, r.sd);
    put16(buf, off + 34, r.fl);
    for (var d = 0; d < 7; d++) {
      put16(buf, off + 36 + 2 * d, r.d[d]);
    }
  });
  sentRows = rows;
  return { BLOB: buf, TIME: data.t, DAY0: data.d0, COUNT: rows.length };
}

function camError(why) {
  console.log('snowscout: webcam failed: ' + why);
  send({ CAM_ERR: why });
}

// Send the converted image: header first, then CAM_CHUNK-byte slices, each after the previous ack
function sendCam(id, img, taken) {
  var header = {
    CAM_W: img.width,
    CAM_H: img.height,
    CAM_PAL: img.palette,
    CAM_TIME: taken,
    CAM_LEN: img.data.length
  };
  var next = function (offset) {
    if (id !== camRequest || offset >= img.data.length) {
      return;
    }
    var end = Math.min(offset + CAM_CHUNK, img.data.length);
    Pebble.sendAppMessage({
      CAM_OFF: offset,
      CAM_DATA: Array.prototype.slice.call(img.data, offset, end)
    }, function () { next(end); }, function () { camError('transfer failed'); });
  };
  Pebble.sendAppMessage(header, function () { next(0); }, function () { camError('transfer failed'); });
}

function fetchCam(index) {
  var r = sentRows[index];
  if (!r || !r.cam) {
    return camError('no webcam');
  }
  var id = ++camRequest;
  var xhr = new XMLHttpRequest();
  xhr.open('GET', r.cam + (r.cam.indexOf('?') < 0 ? '?' : '&') + 't=' + Date.now(), true);
  xhr.responseType = 'arraybuffer';
  xhr.timeout = 30000;
  xhr.onload = function () {
    if (id !== camRequest) {
      return;
    }
    if (xhr.status !== 200 || !xhr.response) {
      return camError('HTTP ' + xhr.status);
    }
    var img;
    try {
      img = cam.convert(xhr.response, CAM_W, CAM_H);
    } catch (e) {
      return camError('not a JPEG');
    }
    var modified = Date.parse(xhr.getResponseHeader('Last-Modified') || '');
    sendCam(id, img, isNaN(modified) ? 0 : Math.round(modified / 1000));
  };
  xhr.onerror = function () { camError('no connection'); };
  xhr.ontimeout = function () { camError('timed out'); };
  xhr.send();
}

function send(msg, tries) {
  tries = tries === undefined ? 3 : tries;
  Pebble.sendAppMessage(msg, function () {}, function () {
    if (tries > 1) {
      setTimeout(function () { send(msg, tries - 1); }, 1000);
    }
  });
}

function fail(why) {
  console.log('snowscout: fetch failed: ' + why);
  send({ STATUS: 'Offline (' + why + ')' });
}

function refresh() {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', DATA_URL + '?t=' + Date.now(), true);
  xhr.timeout = 20000;
  xhr.onload = function () {
    if (xhr.status !== 200) {
      return fail('HTTP ' + xhr.status);
    }
    var data;
    try {
      data = JSON.parse(xhr.responseText);
    } catch (e) {
      return fail('bad data');
    }
    localStorage.setItem('snowscout-data', xhr.responseText);
    send(pack(data, prefs()));
  };
  xhr.onerror = function () { fail('no connection'); };
  xhr.ontimeout = function () { fail('timed out'); };
  xhr.send();
}

Pebble.addEventListener('ready', refresh);

Pebble.addEventListener('appmessage', function (e) {
  if (e.payload && e.payload.CAM_REQ !== undefined) {
    fetchCam(e.payload.CAM_REQ);
  }
});

Pebble.addEventListener('showConfiguration', function () {
  var data = loadJSON('snowscout-data', null);
  var resorts = data ? data.r : [];
  var p = prefs();
  clay.config = buildConfig(resorts);
  // Clay remembers checkboxes by position; reapply ours by id in case the list changed
  clay.setSettings({
    DEFAULT_BOARD: String(p.board),
    FAV: resorts.map(function (r) { return p.fav.indexOf(r.id) >= 0; }),
    HIDE: resorts.map(function (r) { return p.hide.indexOf(r.id) >= 0; })
  });
  Pebble.openURL(clay.generateUrl());
});

Pebble.addEventListener('webviewclosed', function (e) {
  if (!e || !e.response) {
    return;
  }
  var settings = clay.getSettings(e.response, false);
  var data = loadJSON('snowscout-data', null);
  var resorts = data ? data.r : [];
  var ids = function (key) {
    var checked = (settings[key] && settings[key].value) || [];
    return resorts.filter(function (r, i) { return checked[i]; }).map(function (r) { return r.id; });
  };
  var board = parseInt((settings.DEFAULT_BOARD && settings.DEFAULT_BOARD.value) || 0, 10);
  var p = { board: board, fav: ids('FAV'), hide: ids('HIDE') };
  localStorage.setItem('snowscout-prefs', JSON.stringify(p));

  var msg = data ? pack(data, p) : {};
  msg.DEFAULT_BOARD = board;
  send(msg);
});
