
  import { CountUp } from '/static/assets/js/countUp/countUp.min.js';

  window.onload = function() {
    const options = {
      decimalPlaces: 2,
    };
    var countUp = new CountUp('system_balance', 201, options);
    countUp.start();
  }
