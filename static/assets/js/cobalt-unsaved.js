// Used for pages with forms - checks if user tries to leave without saving data

var unsaved = false;

$(":input").change(function(){
    unsaved = true;
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
