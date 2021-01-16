window.onerror =
function (msg, url, num) {

    var errorData = {
      'message': msg,
      'url': url,
      'num': num
    };
    $.post('/support/browser-errors', {
      data: JSON.stringify(errorData)
    });

  return true;
}
