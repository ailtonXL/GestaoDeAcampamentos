document.addEventListener('DOMContentLoaded', () => {
    const body = document.body;
    const sidebar = document.getElementById('sidebar');
    const toggleButton = document.querySelector('[data-sidebar-toggle]');

    if (toggleButton) {
        toggleButton.addEventListener('click', () => {
            body.classList.toggle('sidebar-open');
        });
    }

    document.addEventListener('click', (event) => {
        if (!body.classList.contains('sidebar-open') || !sidebar || !toggleButton) {
            return;
        }

        const clickedInsideSidebar = sidebar.contains(event.target);
        const clickedToggle = toggleButton.contains(event.target);
        if (!clickedInsideSidebar && !clickedToggle) {
            body.classList.remove('sidebar-open');
        }
    });

    const renderChart = (canvasId, config) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !window.Chart) {
            return;
        }

        new Chart(canvas, config);
    };

    const readJson = (elementId, fallback) => {
        const element = document.getElementById(elementId);
        if (!element) {
            return fallback;
        }

        try {
            return JSON.parse(element.textContent);
        } catch (error) {
            return fallback;
        }
    };

    const overviewLabels = readJson('chart-labels', []);
    const overviewValues = readJson('chart-values', []);
    if (overviewLabels.length && overviewValues.length) {
        renderChart('overviewChart', {
            type: 'doughnut',
            data: {
                labels: overviewLabels,
                datasets: [{
                    data: overviewValues,
                    backgroundColor: ['#c79a2d', '#2d6a4f', '#1f8a70'],
                    borderWidth: 0,
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '68%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            pointStyle: 'circle',
                            padding: 20,
                        },
                    },
                },
            },
        });
    }

    const paymentLabels = readJson('payment-chart-labels', []);
    const paymentValues = readJson('payment-chart-values', []);
    if (paymentLabels.length && paymentValues.length) {
        renderChart('paymentChart', {
            type: 'doughnut',
            data: {
                labels: paymentLabels,
                datasets: [{
                    data: paymentValues,
                    backgroundColor: ['#2d6a4f', '#c79a2d'],
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' },
                },
            },
        });
    }

    const inventoryLabels = readJson('inventory-chart-labels', []);
    const inventoryValues = readJson('inventory-chart-values', []);
    if (inventoryLabels.length && inventoryValues.length) {
        renderChart('inventoryChart', {
            type: 'bar',
            data: {
                labels: inventoryLabels,
                datasets: [{
                    label: 'Saldo',
                    data: inventoryValues,
                    backgroundColor: '#2d6a4f',
                    borderRadius: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true },
                },
            },
        });
    }

    const evolutionLabels = readJson('evolution-chart-labels', []);
    const evolutionValues = readJson('evolution-chart-values', []);
    if (evolutionLabels.length && evolutionValues.length) {
        renderChart('evolutionChart', {
            type: 'line',
            data: {
                labels: evolutionLabels,
                datasets: [{
                    label: 'Evolução',
                    data: evolutionValues,
                    borderColor: '#1f8a70',
                    backgroundColor: 'rgba(31, 138, 112, 0.12)',
                    tension: 0.35,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true },
                },
            },
        });
    }

    document.querySelectorAll('.sidebar__link').forEach((link) => {
        const target = link.getAttribute('href');
        if (target && window.location.pathname === target) {
            link.classList.add('is-active');
        }
    });
});
