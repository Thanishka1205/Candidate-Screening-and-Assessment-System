// Basic sorting functionality for table headers
// This script expects the table to be rendered and available in the DOM
// and will sort by clicking on th.sortable

document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('th.sortable').forEach(header => {
        header.addEventListener('click', () => {
            const table = header.closest('table');
            const index = Array.from(header.parentElement.children).indexOf(header);
            const isAscending = header.classList.toggle('asc');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.rows);

            rows.sort((a, b) => {
                const aValue = a.cells[index].textContent.trim();
                const bValue = b.cells[index].textContent.trim();

                // Handle numeric columns (Candidate ID, Attempt #, Score)
                if (index === 0 || index === 3 || index === 4) {
                    const aNum = parseFloat(aValue.replace('%', ''));
                    const bNum = parseFloat(bValue.replace('%', ''));
                    return isAscending ? aNum - bNum : bNum - aNum;
                }

                // Handle date column (Submitted At)
                if (index === 6) {
                    const aDate = aValue === 'N/A' ? 0 : new Date(aValue);
                    const bDate = bValue === 'N/A' ? 0 : new Date(bValue);
                    return isAscending ? aDate - bDate : bDate - aDate;
                }

                // Handle text columns (Full Name, Email)
                return isAscending
                    ? aValue.localeCompare(bValue)
                    : bValue.localeCompare(aValue);
            });

            rows.forEach(row => tbody.appendChild(row));
        });
    });
}); 