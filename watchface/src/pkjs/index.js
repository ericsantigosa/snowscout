// Snowscout Face phone side: fetch data.json and boil it down to what the face shows:
// the 72 h leader, the next big day, and the biggest daily snowfall of each of the next 7 days.
var DATA_URL = 'https://ericsantigosa.github.io/snowscout/data.json';
var BIG_DAY_CM = 10;
var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function dayName(data, d) {
  if (d === 0) {
    return 'Today';
  }
  if (d === 1) {
    return 'Tmrw';
  }
  return WEEKDAYS[new Date((data.d0 + d * 86400 + 43200) * 1000).getDay()];
}

function summarize(data) {
  var top = null;
  data.r.forEach(function (r) {
    if (r.c72 !== null && (!top || r.c72 > top.c72)) {
      top = r;
    }
  });

  var week = [];
  var big = null;
  for (var d = 0; d < 7; d++) {
    var best = null;
    data.r.forEach(function (r) {
      var v = r.d[d];
      if (v !== null && (!best || v > best.v)) {
        best = { r: r, v: v };
      }
    });
    week.push(best ? Math.min(best.v, 255) : 0);
    if (!big && best && best.v >= BIG_DAY_CM) {
      big = { d: d, r: best.r, v: best.v };
    }
  }

  return {
    TIME: data.t,
    DAY0: data.d0,
    WEEK: week,
    LINE_A: top && top.c72 > 0 ? top.n + ' ' + top.c72 + ' cm' : 'No snow forecast',
    LINE_B: big ? dayName(data, big.d) + ': ' + big.r.n + ' ' + big.v + ' cm'
                : 'No ' + BIG_DAY_CM + ' cm day this week'
  };
}

function refresh() {
  var xhr = new XMLHttpRequest();
  xhr.open('GET', DATA_URL + '?t=' + Date.now(), true);
  xhr.timeout = 20000;
  xhr.onload = function () {
    if (xhr.status !== 200) {
      console.log('snowscout face: HTTP ' + xhr.status);
      return;
    }
    try {
      Pebble.sendAppMessage(summarize(JSON.parse(xhr.responseText)));
    } catch (e) {
      console.log('snowscout face: bad data ' + e);
    }
  };
  xhr.onerror = function () { console.log('snowscout face: no connection'); };
  xhr.send();
}

Pebble.addEventListener('ready', refresh);
Pebble.addEventListener('appmessage', function (e) {
  if (e.payload && e.payload.REFRESH !== undefined) {
    refresh();
  }
});
