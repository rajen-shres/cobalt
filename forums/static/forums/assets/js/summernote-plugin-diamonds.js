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
    'specialchardiamonds': function(context) {
      var self = this;
      var ui = $.summernote.ui;
      var $editor = context.layoutInfo.editor;
      var options = context.options;
      var lang = options.langInfo;

      context.memo('button.specialcharsdiamonds', function() {
        return ui.button({
          contents: '<span style="color:red; font-size:12px">&diams;</span>',
          tooltip: 'Diamond',
          click: function() {
            self.show();
          },
        }).render();
      });

      this.initialize = function() {
      };

      this.show = function() {
        context.invoke('editor.pasteHTML', '<span style="color:red">&diams;</span>');
        context.invoke('editor.pasteHTML', '&zwnj;');  // need to move cursor out of span
      };
    }
  });
})
);
