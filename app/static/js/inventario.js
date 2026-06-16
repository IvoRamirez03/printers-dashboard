document.addEventListener('DOMContentLoaded', () => {
    const cells = document.querySelectorAll('.stock-cell');

    cells.forEach(cell => {
        const initialValue = parseInt(cell.getAttribute('data-value'));
        setupCell(cell, initialValue);
    });

    function setupCell(cell, value) {
        cell.innerHTML = `
            <div class="controls">
                <button class="btn-minus">-</button>
                <span class="value-display">${value}</span>
                <button class="btn-plus">+</button>
            </div>
        `;

        updateColor(cell, value);

        const btnMinus = cell.querySelector('.btn-minus');
        const btnPlus = cell.querySelector('.btn-plus');
        const display = cell.querySelector('.value-display');

        btnMinus.addEventListener('click', () => {
            let currentValue = parseInt(display.innerText);
            if (currentValue > 0) {
                currentValue--;
                display.innerText = currentValue;
                updateColor(cell, currentValue);
            }
        });

        btnPlus.addEventListener('click', () => {
            let currentValue = parseInt(display.innerText);
            currentValue++;
            display.innerText = currentValue;
            updateColor(cell, currentValue);
        });
    }

    function updateColor(cell, value) {
        // Limpiar clases previas
        cell.classList.remove('bg-red', 'bg-orange', 'bg-green');

        if (value <= 1) {
            cell.classList.add('bg-red');
        } else if (value === 2) {
            cell.classList.add('bg-orange');
        } else if (value >= 3) {
            cell.classList.add('bg-green');
        }
    }
});