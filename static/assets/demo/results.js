demo = {

  initCharts: function() {

      var dataSimpleBarChart = {
        labels: ['NSWBA', 'NSWBA', 'Trumps', 'SABA', 'Trumps', 'NSWBA', 'Coffs', 'Wests', 'NSBC', 'NSBC'],
        series: [
          [48.5, 53.6, 66.1, 54.6,48.2,57.3,53.7,58.1, 44.3,55.1]
        ]
      };

      var optionsSimpleBarChart = {
        seriesBarDistance: 10,
        axisX: {
          showGrid: false
        }
      };

      var responsiveOptionsSimpleBarChart = [
        ['screen and (max-width: 640px)', {
          seriesBarDistance: 5,
          axisX: {
            labelInterpolationFnc: function(value) {
              return value[0];
            }
          }
        }]
      ];

      var simpleBarChart = Chartist.Bar('#simpleBarChart', dataSimpleBarChart, optionsSimpleBarChart, responsiveOptionsSimpleBarChart);

      md.startAnimationForBarChart(simpleBarChart);

      dataStraightLinesChart = {
        labels: ['Coffs', 'Blue Mnts', 'Trumps', 'Trumps', 'NSBC', 'NSBC', 'Gold Tms', 'Trumps', 'Central Cst'],
        series: [
          [76, 48, 85, 70, 47, 68, 70, 45, 50]
        ]
      };

      optionsStraightLinesChart = {
        lineSmooth: Chartist.Interpolation.cardinal({
          tension: 0
        }),
        low: 0,
        high: 100, // creative tim: we recommend you to set the high sa the biggest value + something for a better look
        chartPadding: {
          top: 20,
          right: 0,
          bottom: 20,
          left: 0
        },
        classNames: {
          point: 'ct-point ct-white',
          line: 'ct-line ct-white'
        }
      }

      var straightLinesChart = new Chartist.Line('#chartPreferences', dataStraightLinesChart, optionsStraightLinesChart);

      md.startAnimationForLineChart(straightLinesChart);


  }
}
