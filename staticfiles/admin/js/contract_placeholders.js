// static/admin/js/contract_placeholders.js
(function($) {
    $(document).ready(function() {
        if (typeof CKEDITOR !== 'undefined') {
            CKEDITOR.on('instanceReady', function(evt) {
                if (evt.editor.name === 'id_body') {
                    initializePlaceholderButtons(evt.editor);
                }
            });
        }
    });

    function initializePlaceholderButtons(editor) {
        const dataElement = document.getElementById('placeholders-data');
        if (!dataElement) return;
        
        const placeholders = JSON.parse(dataElement.textContent);
        
        const mainContainer = document.createElement('div');
        mainContainer.style.padding = '10px 0';
        mainContainer.style.borderTop = '1px solid #eee';
        mainContainer.style.marginTop = '10px';

        const title = document.createElement('h4');
        title.innerText = '可用的佔位符 (點擊插入)';
        title.style.margin = '0 0 10px 0';
        mainContainer.appendChild(title);

        // 按 group 屬性對 placeholders 進行分組
        const groups = {};
        placeholders.forEach(p => {
            if (!groups[p.group]) {
                groups[p.group] = [];
            }
            groups[p.group].push(p);
        });

        // 為每個分組建立按鈕
        for (const groupName in groups) {
            const groupContainer = document.createElement('div');
            groupContainer.style.marginBottom = '10px';

            const groupTitle = document.createElement('strong');
            groupTitle.innerText = groupName;
            groupContainer.appendChild(groupTitle);
            
            const buttonWrapper = document.createElement('div');
            buttonWrapper.style.marginTop = '5px';
            
            groups[groupName].forEach(function(placeholder) {
                const button = document.createElement('button');
                button.type = 'button';
                button.innerText = placeholder.name;
                button.style.marginRight = '5px';
                button.style.marginBottom = '5px';
                button.style.cursor = 'pointer';
                
                button.addEventListener('click', function() {
                    // 對於圖片，我們插入 HTML；對於其他，插入文字
                    if (placeholder.value.startsWith('<img')) {
                        editor.insertHtml(placeholder.value + ' ');
                    } else {
                        editor.insertText(placeholder.value + ' ');
                    }
                });
                
                buttonWrapper.appendChild(button);
            });
            groupContainer.appendChild(buttonWrapper);
            mainContainer.appendChild(groupContainer);
        }
        
        const editorContainer = document.getElementById('cke_id_body');
        if (editorContainer) {
            editorContainer.parentNode.insertBefore(mainContainer, editorContainer.nextSibling);
        }
    }
})(django.jQuery);