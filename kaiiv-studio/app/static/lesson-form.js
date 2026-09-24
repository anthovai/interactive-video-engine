// Show the upload box or the address box, whichever the chosen source needs.
(function() {
    'use strict';
    var radios = document.querySelectorAll('input[name="source"]');
    var toggle = function() {
        var chosen = document.querySelector('input[name="source"]:checked');
        var value = chosen ? chosen.value : 'upload';
        document.querySelectorAll('[data-source]').forEach(function(node) {
            node.hidden = node.getAttribute('data-source').split(' ').indexOf(value) === -1;
        });
    };
    radios.forEach(function(radio) { radio.addEventListener('change', toggle); });
    toggle();
})();
