demo = {

  initCharts: function() {

      dataColouredBarsChart = {
        labels: ['2009', '2010', '2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019'],
        series: [
          [23, 26, 28, 32, 34, 46, 48, 54, 65, 68, 70],
          [210, 230, 230, 280, 310, 410, 480, 490, 513, 521, 536],
          [298, 311, 350, 387, 401, 420, 450, 630, 678, 712, 758]
        ]
      };

      optionsColouredBarsChart = {
        lineSmooth: Chartist.Interpolation.cardinal({
          tension: 10
        }),
        axisY: {
          showGrid: true,
          offset: 40
        },
        axisX: {
          showGrid: false,
        },
        low: 0,
        high: 1000,
        showPoint: true,
        height: '300px'
      };


      var colouredBarsChart = new Chartist.Line('#colouredBarsChart', dataColouredBarsChart, optionsColouredBarsChart);

      md.startAnimationForLineChart(colouredBarsChart);

  },

}
