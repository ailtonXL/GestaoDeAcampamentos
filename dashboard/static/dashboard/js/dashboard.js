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

    const chartCanvas = document.getElementById('overviewChart');
    const labelsElement = document.getElementById('chart-labels');
    const valuesElement = document.getElementById('chart-values');

    if (chartCanvas && labelsElement && valuesElement && window.Chart) {
        const labels = JSON.parse(labelsElement.textContent);
        const values = JSON.parse(valuesElement.textContent);

        new Chart(chartCanvas, {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{
                    data: values,
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

    document.querySelectorAll('.sidebar__link').forEach((link) => {
        const target = link.getAttribute('href');
        if (target && window.location.pathname === target) {
            link.classList.add('is-active');
        }
    });
});
