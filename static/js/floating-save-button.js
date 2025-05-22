// 悬浮保存按钮功能
document.addEventListener('DOMContentLoaded', function() {
    const globalSaveButton = document.getElementById('global-save-button');
    const saveToast = document.getElementById('save-toast');
    
    // 初始隐藏悬浮按钮，只在API配置页面显示
    if (globalSaveButton) {
        // 默认隐藏按钮
        globalSaveButton.style.display = 'none';
        
        // 检查当前是否在API配置页面
        const apiConfigSection = document.getElementById('api-config-section');
        if (apiConfigSection && window.getComputedStyle(apiConfigSection).display !== 'none') {
            globalSaveButton.style.display = 'flex';
        }
        
        // 监听导航项点击事件，控制按钮显示/隐藏
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => {
            item.addEventListener('click', function() {
                const sectionId = this.getAttribute('data-section');
                if (sectionId === 'api-config') {
                    globalSaveButton.style.display = 'flex';
                } else {
                    globalSaveButton.style.display = 'none';
                }
            });
        });
        
        // 点击悬浮保存按钮时收集并保存全局设置
        globalSaveButton.addEventListener('click', function() {
            // 防止重复点击
            if (globalSaveButton.classList.contains('saving')) {
                return;
            }

            // 设置按钮为保存中状态
            globalSaveButton.classList.add('saving');

            // 收集全局配置
            const config = collectGlobalConfig();

            // 发送配置到服务器
            fetch('/api/update_api_config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 更新主页卡片上的模型显示
                    updateModelDisplay(config);
                    
                    // 显示保存成功提示
                    showSaveToast();
                } else {
                    alert('保存全局设置失败: ' + data.error);
                }
            })
            .catch(error => {
                alert('保存全局设置出错: ' + error);
            })
            .finally(() => {
                // 恢复按钮状态
                globalSaveButton.classList.remove('saving');
            });
        });
    }

    // 收集全局配置
    function collectGlobalConfig() {
        // 获取API类型
        const useOnlineApi = document.getElementById('use-online-api')?.checked || false;

        // 基本配置
        const config = {
            use_online_api: useOnlineApi
        };

        // Ollama API配置
        if (!useOnlineApi) {
            config.ollama_api_url = document.getElementById('ollama-api-url')?.value || "http://127.0.0.1:11434";
            // 获取选中的Ollama模型
            const ollamaModelSelect = document.getElementById('ollama-model-select');
            if (ollamaModelSelect) {
                config.selected_ollama_model = ollamaModelSelect.value;
            }
        }
        // 在线API配置
        else {
            config.online_api_url = document.getElementById('online-api-url')?.value || "";
            config.online_api_key = document.getElementById('online-api-key')?.value || "";
            config.online_api_model = document.getElementById('online-model-name')?.value || "";
        }

        // 分析模型配置
        const analysisModelRadio = document.querySelector('input[name="analysis-model"]:checked');
        if (analysisModelRadio) {
            const analysisModelValue = analysisModelRadio.value;
            config.analysis_model_name = analysisModelValue;

            if (analysisModelValue === 'custom') {
                const analysisCustomTypeRadio = document.querySelector('input[name="analysis-custom-type"]:checked');
                if (analysisCustomTypeRadio) {
                    config.analysis_custom_type = analysisCustomTypeRadio.value;

                    if (config.analysis_custom_type === 'ollama') {
                        config.analysis_custom_ollama_model = document.getElementById('analysis-ollama-model-select')?.value || "";
                    } else {
                        config.analysis_custom_online_model = document.getElementById('analysis-online-model-name')?.value || "";
                    }
                }
            }
        }

        // 写作模型配置
        const writingModelRadio = document.querySelector('input[name="writing-model"]:checked');
        if (writingModelRadio) {
            const writingModelValue = writingModelRadio.value;
            config.writing_model_name = writingModelValue;

            if (writingModelValue === 'custom') {
                const writingCustomTypeRadio = document.querySelector('input[name="writing-custom-type"]:checked');
                if (writingCustomTypeRadio) {
                    config.writing_custom_type = writingCustomTypeRadio.value;

                    if (config.writing_custom_type === 'ollama') {
                        config.writing_custom_ollama_model = document.getElementById('writing-ollama-model-select')?.value || "";
                    } else {
                        config.writing_custom_online_model = document.getElementById('writing-online-model-name')?.value || "";
                    }
                }
            }
        }

        return config;
    }

    // 更新主页卡片上的模型显示
    function updateModelDisplay(config) {
        const analysisModelDisplay = document.querySelector('.model-info:nth-child(1) .model-value');
        const writingModelDisplay = document.querySelector('.model-info:nth-child(2) .model-value');

        if (analysisModelDisplay) {
            analysisModelDisplay.textContent = config.analysis_model_name;
        }

        if (writingModelDisplay) {
            writingModelDisplay.textContent = config.writing_model_name;
        }
    }

    // 显示保存成功提示
    function showSaveToast() {
        saveToast.classList.add('show');
        
        // 3秒后自动隐藏
        setTimeout(() => {
            saveToast.classList.remove('show');
        }, 3000);
    }
});
