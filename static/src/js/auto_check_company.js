// document.addEventListener('DOMContentLoaded', function () {
//     const targetCompanyId = '1'; // Michel J. Lhuillier

//     // --- Helpers ---
//     function simulateClick(el) {
//         if (!el) return;
//         ['mousedown', 'mouseup', 'click'].forEach(type => {
//             const evt = new MouseEvent(type, { bubbles: true, cancelable: true, view: window });
//             el.dispatchEvent(evt);
//         });
//     }

//     function q(sel, root = document) { return root.querySelector(sel); }
//     function qa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

//     // --- Ensure checkboxes are visually checked (click only if needed) ---
//     function ensureCheckboxesChecked(items) {
//         items.forEach(item => {
//             const checkboxIcon = q('[role="menuitemcheckbox"] i', item);
//             if (checkboxIcon && !checkboxIcon.classList.contains('fa-check-square')) {
//                 console.debug('Checking checkbox for company', item.getAttribute('data-company-id'));
//                 simulateClick(checkboxIcon);
//             }
//         });
//     }

//     // --- Prevent other companies from being chosen as the active company ---
//     function blockOtherCompanyClicks(items) {
//         items.forEach(item => {
//             const companyId = item.getAttribute('data-company-id');
//             const logBtn = q('.log_into', item);
//             if (!logBtn) return;
//             if (companyId === targetCompanyId) return; // don't block target

//             // add blocking only once
//             if (logBtn.dataset.__blocked) return;
//             logBtn.dataset.__blocked = 'true';

//             logBtn.addEventListener('click', function (ev) {
//                 ev.stopImmediatePropagation();
//                 ev.preventDefault();
//                 console.warn('Blocked attempt to switch to company', companyId);
//                 // re-enforce Michel selection
//                 setTimeout(() => enforceMichel(), 50);
//             }, true); // capture to stop earlier
//         });
//     }

//     // --- Make Michel the active company (click only if not active) ---
//     function activateMichelIfNeeded(items) {
//         const targetItem = items.find(i => i.getAttribute('data-company-id') === targetCompanyId);
//         if (!targetItem) {
//             console.warn('Target company item not found yet');
//             return;
//         }
//         const logBtn = q('.log_into', targetItem);
//         if (!logBtn) return;

//         const isActive = logBtn.classList.contains('bg-primary-subtle') || logBtn.getAttribute('aria-pressed') === 'true';
//         if (!isActive) {
//             console.info('Activating Michel (company id=' + targetCompanyId + ')');
//             simulateClick(logBtn);

//             // If Odoo shows a confirm button, click it quickly to apply selection
//             setTimeout(() => {
//                 const confirm = q('.o_switch_company_menu_buttons .btn.btn-primary');
//                 if (confirm) {
//                     console.debug('Clicking confirm button for company switch');
//                     simulateClick(confirm);
//                 }
//             }, 200);
//         }
//     }

//     // --- Ensure non-target companies do not have active styling ---
//     function clearActiveFromOthers(items) {
//         items.forEach(item => {
//             const companyId = item.getAttribute('data-company-id');
//             if (companyId === targetCompanyId) return;
//             const logBtn = q('.log_into', item);
//             if (!logBtn) return;
//             if (logBtn.classList.contains('bg-primary-subtle')) {
//                 logBtn.classList.remove('bg-primary-subtle');
//             }
//             if (logBtn.getAttribute('aria-pressed') === 'true') {
//                 logBtn.setAttribute('aria-pressed', 'false');
//             }
//         });
//     }

//     // --- Main enforcement function ---
//     function enforceMichel() {
//         const items = qa('.o_switch_company_item');
//         if (!items || items.length === 0) {
//             // menu not present yet
//             return;
//         }
//         console.debug('enforceMichel running, found', items.length, 'items');

//         // 1) Ensure all checkboxes are checked (visually)
//         ensureCheckboxesChecked(items);

//         // 2) Block clicks on other companies' log_in buttons
//         blockOtherCompanyClicks(items);

//         // 3) Activate Michel if it's not active
//         activateMichelIfNeeded(items);

//         // 4) Clear active styling from non-targets (visual safety)
//         clearActiveFromOthers(items);
//     }

//     // --- Initial run with small delay to let menu build ---
//     setTimeout(() => {
//         enforceMichel();
//     }, 600);

//     // --- MutationObserver to re-enforce whenever Odoo updates the menu DOM ---
//     let debounceTimer = null;
//     const observer = new MutationObserver(() => {
//         if (debounceTimer) clearTimeout(debounceTimer);
//         debounceTimer = setTimeout(() => {
//             enforceMichel();
//         }, 120);
//     });
//     observer.observe(document.body, { childList: true, subtree: true });

//     console.info('Michel-enforcer script loaded (target company id=' + targetCompanyId + ')');
// });










document.addEventListener('DOMContentLoaded', function () {
    const targetCompanyName = "MICHEL J. LHUILLIER FINANCIAL SERVICES (PAWNSHOPS) INC.";

    // --- Inject CSS to hide the entire company switcher (button + menu) ---
    const style = document.createElement('style');
    style.textContent = `
        /* Hide the dropdown button itself */
        .o_switch_company_menu button.o-dropdown.dropdown-toggle {
            display: none !important;
            visibility: hidden !important;
        }
        /* Hide the dropdown items */
        .o_switch_company_menu_items {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
        }
    `;
    document.head.appendChild(style);

    // --- Helpers ---
    function simulateClick(el) {
        if (!el) return;
        ['mousedown', 'mouseup', 'click'].forEach(type => {
            const evt = new MouseEvent(type, { bubbles: true, cancelable: true, view: window });
            el.dispatchEvent(evt);
        });
    }

    function q(sel, root = document) { return root.querySelector(sel); }
    function qa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

    function getCompanyName(item) {
        const labelEl = q('.company_label', item);
        return labelEl ? labelEl.textContent.trim() : "";
    }

    // --- Ensure checkboxes are visually checked ---
    function ensureCheckboxesChecked(items) {
        items.forEach(item => {
            const checkboxIcon = q('[role="menuitemcheckbox"] i', item);
            if (checkboxIcon && !checkboxIcon.classList.contains('fa-check-square')) {
                simulateClick(checkboxIcon);
            }
        });
    }

    // --- Block other companies from being switched into ---
    function blockOtherCompanyClicks(items) {
        items.forEach(item => {
            const companyName = getCompanyName(item);
            const logBtn = q('.log_into', item);
            if (!logBtn) return;
            if (companyName === targetCompanyName) return;

            if (logBtn.dataset.__blocked) return;
            logBtn.dataset.__blocked = 'true';

            logBtn.addEventListener('click', function (ev) {
                ev.stopImmediatePropagation();
                ev.preventDefault();
                enforceMichel();
            }, true);
        });
    }

    // --- Ensure Michel is the active company ---
    function activateMichelIfNeeded(items) {
        const targetItem = items.find(i => getCompanyName(i) === targetCompanyName);
        if (!targetItem) return;
        const logBtn = q('.log_into', targetItem);
        if (!logBtn) return;

        const isActive = logBtn.classList.contains('bg-primary-subtle') || logBtn.getAttribute('aria-pressed') === 'true';
        if (!isActive) {
            simulateClick(logBtn);
            setTimeout(() => {
                const confirm = q('.o_switch_company_menu_buttons .btn.btn-primary');
                if (confirm) simulateClick(confirm);
            }, 200);
        }
    }

    // --- Remove active state from others ---
    function clearActiveFromOthers(items) {
        items.forEach(item => {
            const companyName = getCompanyName(item);
            if (companyName === targetCompanyName) return;
            const logBtn = q('.log_into', item);
            if (!logBtn) return;
            logBtn.classList.remove('bg-primary-subtle');
            if (logBtn.getAttribute('aria-pressed') === 'true') {
                logBtn.setAttribute('aria-pressed', 'false');
            }
        });
    }

    // --- Main enforcement ---
    function enforceMichel() {
        const items = qa('.o_switch_company_item');
        if (!items || items.length === 0) return;

        ensureCheckboxesChecked(items);
        blockOtherCompanyClicks(items);
        activateMichelIfNeeded(items);
        clearActiveFromOthers(items);
    }

    // Run once after load
    setTimeout(() => enforceMichel(), 600);

    // Watch DOM for redraws
    let debounceTimer = null;
    const observer = new MutationObserver(() => {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => enforceMichel(), 120);
    });
    observer.observe(document.body, { childList: true, subtree: true });
});
