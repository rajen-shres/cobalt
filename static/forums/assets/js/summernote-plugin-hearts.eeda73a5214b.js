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
    'specialcharhearts': function(context) {
      var self = this;
      var ui = $.summernote.ui;
      var $editor = context.layoutInfo.editor;
      var options = context.options;
      var lang = options.langInfo;

      context.memo('button.specialcharshearts', function() {
        return ui.button({
          contents: '<span style="color:red; font-size:12px">&hearts;</span>',
          tooltip: 'Heart',
          click: function() {
            self.show();
          },
        }).render();
      });

      this.initialize = function() {
      };

      this.show = function() {
        context.invoke('editor.pasteHTML', '<span style="color:red">&hearts;</span>');
        context.invoke('editor.pasteHTML', '&zwnj;');
      };
    }
  });
})
);
