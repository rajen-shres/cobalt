demo = {

  initCharts: function() {

      dataColouredBarsChart = {
        series: [
          [135,123,123,123,83,83,83,71,71,136,124,124,112,112,112,72,72,172,172,172,160,160,160,125,125,125,113,113,101,101,101]
        ]
      };



      optionsColouredBarsChart = {
          lineSmooth: Chartist.Interpolation.cardinal({
            tension: 0
          }),
          low: 0,
          high: 220, // creative tim: we recommend you to set the high sa the biggest value + something for a better look
          chartPadding: {
            top: 0,
            right: 0,
            bottom: 0,
            left: 0
          },
          classNames: {
            point: 'ct-point ct-white',
            line: 'ct-line ct-white'
          }
        }


      var colouredBarsChart = new Chartist.Line('#colouredBarsChart', dataColouredBarsChart, optionsColouredBarsChart);

      md.startAnimationForLineChart(colouredBarsChart);

  },

}
