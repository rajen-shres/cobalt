(function(factory) {
  if (typeof define === 'function' && define.amd) {
    // AMD. Register as an anonymous module.
    define(['jquery'], factory);
  } else if (typeof module === 'object' && module.exports) {
    // Node/CommonJS
    module.exports = factory(require('jquery'));
  } else {
    // Browser globals
    factory(window.jQuery);
  }
}(function($) {


  $.extend($.summernote.plugins, {
    'specialcharclubs': function(context) {
      var self = this;
      var ui = $.summernote.ui;
      var $editor = context.layoutInfo.editor;
      var options = context.options;
      var lang = options.langInfo;

      context.memo('button.specialcharsclubs', function() {
        return ui.button({
          contents: '<span style="font-size:12px">&clubs;</span>',
          tooltip: 'Club',
          click: function() {
            self.show();
          },
        }).render();
      });

      this.initialize = function() {
      };

      this.show = function() {
        var text = context.invoke('editor.getSelectedText');
        context.invoke('editor.saveRange');
        context.invoke('editor.restoreRange');

        var $node = $('<span></span>').html(decodeURIComponent('&clubs;'))[0];

        context.invoke('editor.insertNode', $node);


      };
    }
  });
})
);
