// Clay settings page, built from the resort list of the last data.json the phone saw.
var REGION = { CAT: 'Catalonia', AND: 'Andorra', FR: 'France' };

module.exports = function (resorts) {
  var names = resorts.map(function (r) { return r.n + ' (' + (REGION[r.reg] || r.reg) + ')'; });
  var none = resorts.map(function () { return false; });

  var config = [
    { type: 'heading', defaultValue: 'Snowscout' },
    {
      type: 'section',
      items: [
        { type: 'heading', defaultValue: 'Display' },
        {
          type: 'select',
          messageKey: 'DEFAULT_BOARD',
          label: 'Board shown first',
          defaultValue: '0',
          options: [
            { label: 'Next 72 h', value: '0' },
            { label: 'Fresh 48 h', value: '1' },
            { label: 'Snow depth', value: '2' },
            { label: 'Open slopes', value: '3' }
          ]
        }
      ]
    }
  ];

  if (!resorts.length) {
    config.push({
      type: 'text',
      defaultValue: 'Open Snowscout on the watch once so the resort list loads, then come back here.'
    });
  } else {
    config.push({
      type: 'section',
      items: [
        { type: 'heading', defaultValue: 'Favourites' },
        { type: 'text', defaultValue: 'Shown at the top of every board.' },
        { type: 'checkboxgroup', messageKey: 'FAV', label: 'Favourite resorts', defaultValue: none, options: names }
      ]
    });
    config.push({
      type: 'section',
      items: [
        { type: 'heading', defaultValue: 'Hidden resorts' },
        { type: 'checkboxgroup', messageKey: 'HIDE', label: 'Hide these resorts', defaultValue: none, options: names }
      ]
    });
  }

  config.push({ type: 'submit', defaultValue: 'Save' });
  return config;
};
