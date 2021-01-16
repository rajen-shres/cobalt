//------------------------------------------------------------------------//
// Cobalt Core JS functions, loaded on all pages by default               //
// from base.html template.                                               //
//                                                                        //
// This does the following:                                               //
//                                                                        //
// 1) Intercepts errors and sends them to the server to log               //
// 2) Stops designated submit buttons from being pressed twice            //
// 3) Warns a user if they try to leave a page with changes on it         //
//                                                                        //
// if anything on the page has id=ignore_cobalt_save then we ignore the   //
// checks.                                                                //
//                                                                        //
// if any button has class cobalt-save then we will disable them when     //
// a form is submitted and we will ignore the check for changes if they   //
// are clicked. If any other button or navigation is used then if data    //
// has changed, the user will be warned.                                  //
//                                                                        //
//------------------------------------------------------------------------//

// Global var to track changes to form fields

var cobalt_form_data_changed = false;

//------------------------------------------------//
// send client side errors to the server to log   //
//------------------------------------------------//

window.onerror =
function (message, source, lineno, colno, error) {
    console.log(message);
    console.log(source);
    console.log(lineno);
    var errorData = {
      'message': message,
      'url': source,
      'num': lineno,
      'colno': colno,
      'Error object': JSON.stringify(error)
    };
    $.post('/support/browser-errors', {
      data: JSON.stringify(errorData)
    });

  return true;
}

//----------------------------------------------------------------------//
// async function to disable buttons - called by doc ready function     //
//----------------------------------------------------------------------//

function disable_submit_button() {
    $(".cobalt-save").each(function() {
      $(this).prop('disabled', true);
  });
};

// function reset_cobalt_unsaved() {
//   // allow page to force us to ignore unsaved changes
//   console.log("called reset");
//   unsaved = false;
// }

//----------------------------------//
//  Document Ready Activities       //
//----------------------------------//

$(document).ready(function () {

  //------------------------------------------------------------//
  // block user from double clicking on a submit button.        //
  // Any button of class cobalt-save will be disabled when      //
  // a cobalt-save button is clicked                            //
  //------------------------------------------------------------//

  $(".cobalt-save").click(function () {

    // only disable buttons if client side validation has passed
    // uses jquery validation plugin
    try {
      // may not be a form to use, try catch
      var form = $(this.form);
      form.validate();
        if ($(this.form).valid()){
          setTimeout(function () { disable_submit_button(); }, 0);
        }
    } catch (error) {
      // if no form then we don't need to disable the buttons
    }
  });

  //--------------------------------------------------------------------//
  // Listen to any object that is an input                              //
  // if object has class cobalt-save then it is a save button so ignore //
  // else set cobalt_form_data_changed to true                          //
  //--------------------------------------------------------------------//

  $(":input").change(function(){

    var myClass = $(this).attr("class");
    if (myClass != null) {
      if (myClass.indexOf("cobalt-save") == -1){
        cobalt_form_data_changed = true;
      }
    }
  });

  //------------------------------------------------------------------//
  // If a button of class cobalt-save is pressed, ignore changed data //
  //------------------------------------------------------------------//

  $('.cobalt-save').click(function() {
      cobalt_form_data_changed = false;
  });

  //---------------------------------------------------//
  // Function to call when page is unloaded           //
  //---------------------------------------------------//

  function unloadPage(){
    // check if this page wants to be ignored
    // if any object is called ignore_cobalt_save then do nothing
    var ignore=$("#ignore_cobalt_save");
    if (ignore.attr('id') == null){
      if(cobalt_form_data_changed){
          return "You have unsaved changes on this page. Do you want to leave this page and discard your changes or stay on this page?";
      }
    }
  }

  //----------------------------------------//
  // register function                      //
  //----------------------------------------//
  window.onbeforeunload = unloadPage;

});
