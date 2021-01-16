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
    'specialcharshand': function(context) {
      var self = this;
      var ui = $.summernote.ui;
      var $editor = context.layoutInfo.editor;
      var options = context.options;
      var lang = options.langInfo;

      context.memo('button.specialcharshand', function() {
        return ui.button({
          contents: '<script src="https://kit.fontawesome.com/a076d05399.js"></script><i class="fas fa-hand-paper">',
          tooltip: 'Hand',
          click: function() {
            self.show();
          },
        }).render();
      });

      this.initialize = function() {
      };


      this.show = function() {

        var html = `
        <div  style="width:800px; margin:0 auto;">
        <table>
  <tr>
    <td width="180" height="180" style="vertical-align: top;text-align: left;line-height:0.1">
      <p> </p>
      <p><b>Board ?</b></p>
      <p><b>Dealer ?</b></p>
      <p><b>Vul ?</b></p>
    </td>
    <td width="180" height="180">
      <div style=" width: 50%;margin: 0 auto;line-height:0.1">
        <h4>North</h4>
        <table>
          <tr><td><p style="font-size:15px">&spades;</td><td style="font-size:15px">A</p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&hearts;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&diams;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px">&clubs;</td><td style="font-size:15px">A</p></td></tr>
        </table>
      </div>
    </td>
    <td width="180" height="180"></td>
  </tr>
  <tr>
    <td width="180" height="180">
    <div style=" width: 50%;margin: 0 auto;line-height:0.1">
        <h4>West</h4>
          <table>
            <tr><td><p style="font-size:15px">&spades;</td><td style="font-size:15px">A</p></td></tr>
            <tr><td><p style="font-size:15px"><span style="color:red">&hearts;</td><td style="font-size:15px">A</span></p></td></tr>
            <tr><td><p style="font-size:15px"><span style="color:red">&diams;</td><td style="font-size:15px">A</span></p></td></tr>
            <tr><td><p style="font-size:15px">&clubs;</td><td style="font-size:15px">A</p></td></tr>
          </table>
      </div>
    </td>
    <td width="100" height="100" style="background-color:green"></td>
    <td width="180" height="180">
    <div style=" width: 50%;margin: 0 auto;line-height:0.1">
        <h4>East</h4>
        <table>
          <tr><td><p style="font-size:15px">&spades;</td><td style="font-size:15px">A</p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&hearts;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&diams;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px">&clubs;</td><td style="font-size:15px">A</p></td></tr>
        </table>
      </div>
    </td>
  </tr>
  <tr>
    <td width="180" height="180"></td>
    <td width="180" height="180">
    <div style=" width: 50%;margin: 0 auto;line-height:0.1">
        <h4>South</h4>
        <table>
          <tr><td><p style="font-size:15px">&spades;</td><td style="font-size:15px">A</p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&hearts;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px"><span style="color:red">&diams;</td><td style="font-size:15px">A</span></p></td></tr>
          <tr><td><p style="font-size:15px">&clubs;</td><td style="font-size:15px">A</p></td></tr>
        </table>
      </div>
    </td>
    <td width="180" height="180"></td>
  </tr>
</table>
</div>


`;


        context.invoke('editor.pasteHTML', html);
        context.invoke('editor.pasteHTML', '&zwnj;');  // need to move cursor out of span



      };
    }
  });
})
);
