// // Set new default font family and font color to mimic Bootstrap's default styling
// Chart.defaults.global.defaultFontFamily = 'Nunito', '-apple-system,system-ui,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif';
// Chart.defaults.global.defaultFontColor = '#858796';

// // Create a new chart instance
// var ctx = document.getElementById("myPieChart");
// var myPieChart = new Chart(ctx, {
//   type: 'doughnut',
//   data: {
//     labels: [], // Labels will be updated with API data
//     datasets: [{
//       data: [], // Data will be updated with API data
//       backgroundColor: ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e'],
//       hoverBackgroundColor: ['#2e59d9', '#17a673', '#2c9faf', '#f5c6cb'],
//       hoverBorderColor: "rgba(234, 236, 244, 1)",
//     }],
//   },
//   options: {
//     maintainAspectRatio: false,
//     tooltips: {
//       backgroundColor: "rgb(255,255,255)",
//       bodyFontColor: "#858796",
//       borderColor: '#dddfeb',
//       borderWidth: 1,
//       xPadding: 15,
//       yPadding: 15,
//       displayColors: false,
//       caretPadding: 10,
//     },
//     legend: {
//       display: false
//     },
//     cutoutPercentage: 80,
//   },
// });

// // Function to fetch data from the API and update the chart
// function carregarDadosPizza() {
//   fetch('http://127.0.0.1:8000/agenda/default/despesas_categoria_api')
//     .then(response => response.json())
//     .then(data => {
//       var dadosCategorias = data.dados;

//       // Update chart data
//       myPieChart.data.labels = Object.keys(dadosCategorias);
//       myPieChart.data.datasets[0].data = Object.values(dadosCategorias);
//       myPieChart.update();
//     })
//     .catch(error => console.error('Erro ao carregar dados:', error));
// }

// // Load data and initialize the chart
// document.addEventListener('DOMContentLoaded', function () {
//   carregarDadosPizza();
// });
