// send client side errors to the server to log
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

// async function to disable buttons
function disable_submit_button() {
    $(".cobalt-save").each(function() {
      $(this).prop('disabled', true);
      // $(this).classList.add('disabled');
      // $(this).setAttribute('data-original', btn.textContent);
      // $(this).textContent = "Running..."
  });
};

$(document).ready(function () {

  // block user from double clicking on a submit button.
  // Any button of class cobalt-save will be disabled when
  // a cobalt-save button is clicked

  $(".cobalt-save").click(function () {

    // only disable buttons if client side validation has passed
    // uses jquery validation plugin
    try {
      // may not be a form to use try catch
      var form = $(this.form);
      form.validate();
        if ($(this.form).valid()){
          setTimeout(function () { disable_submit_button(); }, 0);
        }
    } catch (error) {
      // if no form then we don't need to disable the buttons 
      console.error(error);
    }



  });

  // prompt for unsaved changes unless button is cobalt-save

  var unsaved = false;

  $(":input").change(function(){

    // check if object has class cobalt-save and ignore
    // else set unsaved to true
    var myClass = $(this).attr("class");
    if (myClass.indexOf("cobalt-save") == -1){
      unsaved = true;
    }
  });

  $('.cobalt-save').click(function() {
      unsaved = false;
  });

  function unloadPage(){
      if(unsaved){
          return "You have unsaved changes on this page. Do you want to leave this page and discard your changes or stay on this page?";
      }
  }

  window.onbeforeunload = unloadPage;


});
