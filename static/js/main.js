// 修复版本的main.js
document.addEventListener('DOMContentLoaded', function() {
    // 导航切换
    const navItems = document.querySelectorAll('.nav-item');
    const contentSections = document.querySelectorAll('.content-section');

    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const sectionId = this.getAttribute('data-section');

            // 更新导航项激活状态
            navItems.forEach(nav => nav.classList.remove('active'));
            this.classList.add('active');

            // 显示对应内容区域
            contentSections.forEach(section => {
                section.style.display = 'none';
            });
            document.getElementById(sectionId + '-section').style.display = 'block';
            
            // 如果切换到API配置页面，自动刷新模型列表
            if (sectionId === 'api-config') {
                refreshOllamaModels();
            }
        });
    });

    // 文件上传按钮美化
    const fileInput = document.getElementById('novel-file');
    const fileNameDisplay = document.getElementById('file-name-display');

    if (fileInput && fileNameDisplay) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                fileNameDisplay.textContent = this.files[0].name;
            } else {
                fileNameDisplay.textContent = '未选择文件';
            }
        });
    }

    // API类型切换
    const useLocalApi = document.getElementById('use-local-api');
    const useOnlineApi = document.getElementById('use-online-api');
    const ollamaApiConfig = document.getElementById('ollama-api-config');
    const onlineApiConfig = document.getElementById('online-api-config');

    if (useLocalApi && useOnlineApi) {
        useLocalApi.addEventListener('change', function() {
            if (this.checked) {
                ollamaApiConfig.style.display = 'block';
                onlineApiConfig.style.display = 'none';
            }
        });

        useOnlineApi.addEventListener('change', function() {
            if (this.checked) {
                ollamaApiConfig.style.display = 'none';
                onlineApiConfig.style.display = 'block';
            }
        });
    }

    // 自定义分析模型设置
    const analysisModelOptions = document.querySelectorAll('input[name="analysis-model"]');
    const analysisCustomSettings = document.getElementById('analysis-custom-settings');

    if (analysisModelOptions.length > 0 && analysisCustomSettings) {
        analysisModelOptions.forEach(option => {
            option.addEventListener('change', function() {
                if (this.value === 'custom' && this.checked) {
                    analysisCustomSettings.style.display = 'block';
                } else if (this.checked) {
                    analysisCustomSettings.style.display = 'none';
                }
            });
        });
    }

    // 自定义分析模型类型切换
    const analysisCustomOllama = document.getElementById('analysis-custom-ollama');
    const analysisCustomOnline = document.getElementById('analysis-custom-online');
    const analysisCustomOllamaSettings = document.getElementById('analysis-custom-ollama-settings');
    const analysisCustomOnlineSettings = document.getElementById('analysis-custom-online-settings');

    if (analysisCustomOllama && analysisCustomOnline) {
        analysisCustomOllama.addEventListener('change', function() {
            if (this.checked) {
                analysisCustomOllamaSettings.style.display = 'block';
                analysisCustomOnlineSettings.style.display = 'none';
            }
        });

        analysisCustomOnline.addEventListener('change', function() {
            if (this.checked) {
                analysisCustomOllamaSettings.style.display = 'none';
                analysisCustomOnlineSettings.style.display = 'block';
            }
        });
    }

    // 自定义写作模型设置
    const writingModelOptions = document.querySelectorAll('input[name="writing-model"]');
    const writingCustomSettings = document.getElementById('writing-custom-settings');

    if (writingModelOptions.length > 0 && writingCustomSettings) {
        writingModelOptions.forEach(option => {
            option.addEventListener('change', function() {
                if (this.value === 'custom' && this.checked) {
                    writingCustomSettings.style.display = 'block';
                } else if (this.checked) {
                    writingCustomSettings.style.display = 'none';
                }
            });
        });
    }

    // 自定义写作模型类型切换
    const writingCustomOllama = document.getElementById('writing-custom-ollama');
    const writingCustomOnline = document.getElementById('writing-custom-online');
    const writingCustomOllamaSettings = document.getElementById('writing-custom-ollama-settings');
    const writingCustomOnlineSettings = document.getElementById('writing-custom-online-settings');

    if (writingCustomOllama && writingCustomOnline) {
        writingCustomOllama.addEventListener('change', function() {
            if (this.checked) {
                writingCustomOllamaSettings.style.display = 'block';
                writingCustomOnlineSettings.style.display = 'none';
            }
        });

        writingCustomOnline.addEventListener('change', function() {
            if (this.checked) {
                writingCustomOllamaSettings.style.display = 'none';
                writingCustomOnlineSettings.style.display = 'block';
            }
        });
    }

    // 刷新Ollama模型列表
    const refreshModelsBtn = document.getElementById('refresh-models-btn');

    // 页面加载时自动刷新模型列表
    function refreshOllamaModels() {
        const ollamaApiUrl = document.getElementById('ollama-api-url').value;

        if (!ollamaApiUrl) {
            console.log('Ollama API URL未设置，跳过自动刷新模型列表');
            return;
        }

        // 如果有刷新按钮，显示加载状态
        if (refreshModelsBtn) {
            refreshModelsBtn.disabled = true;
            refreshModelsBtn.textContent = '正在获取模型列表...';
        }

        // 发送请求获取模型列表
        fetch('/api/refresh_ollama_models', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                api_url: ollamaApiUrl
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 更新分析模型下拉列表
                const analysisOllamaModelSelect = document.getElementById('analysis-ollama-model-select');
                if (analysisOllamaModelSelect) {
                    analysisOllamaModelSelect.innerHTML = '';

                    data.models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        analysisOllamaModelSelect.appendChild(option);
                    });
                }

                // 更新写作模型下拉列表
                const writingOllamaModelSelect = document.getElementById('writing-ollama-model-select');
                if (writingOllamaModelSelect) {
                    writingOllamaModelSelect.innerHTML = '';

                    data.models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        writingOllamaModelSelect.appendChild(option);
                    });
                }

                console.log('模型列表已更新');
            } else {
                console.error('获取模型列表失败:', data.error);
            }
        })
        .catch(error => {
            console.error('获取模型列表出错:', error);
        })
        .finally(() => {
            // 恢复按钮状态
            if (refreshModelsBtn) {
                refreshModelsBtn.disabled = false;
                refreshModelsBtn.textContent = '刷新模型列表';
            }
        });
    }

    // 如果存在刷新按钮，添加点击事件
    if (refreshModelsBtn) {
        refreshModelsBtn.addEventListener('click', refreshOllamaModels);
    }

    // 页面加载时自动刷新一次模型列表
    setTimeout(refreshOllamaModels, 500);

    // API配置表单提交
    const apiConfigForm = document.getElementById('api-config-form');

    if (apiConfigForm) {
        apiConfigForm.addEventListener('submit', function(e) {
            e.preventDefault();

            // 获取API类型
            const useOnlineApi = document.getElementById('use-online-api').checked;

            // 基本配置
            const config = {
                use_online_api: useOnlineApi
            };

            // Ollama API配置
            if (!useOnlineApi) {
                config.ollama_api_url = document.getElementById('ollama-api-url').value;
                // 获取选中的Ollama模型
                const ollamaModelSelect = document.getElementById('ollama-model-select');
                if (ollamaModelSelect) {
                    config.selected_ollama_model = ollamaModelSelect.value;
                }
            }
            // 在线API配置
            else {
                config.online_api_url = document.getElementById('online-api-url').value;
                config.online_api_key = document.getElementById('online-api-key').value;
                config.online_api_model = document.getElementById('online-model-name').value;
            }

            // 分析模型配置
            const analysisModelValue = document.querySelector('input[name="analysis-model"]:checked').value;
            config.analysis_model_name = analysisModelValue;

            if (analysisModelValue === 'custom') {
                config.analysis_custom_type = document.querySelector('input[name="analysis-custom-type"]:checked').value;

                if (config.analysis_custom_type === 'ollama') {
                    config.analysis_custom_ollama_model = document.getElementById('analysis-ollama-model-select').value;
                } else {
                    config.analysis_custom_online_model = document.getElementById('analysis-online-model-name').value;
                }
            }

            // 写作模型配置
            const writingModelValue = document.querySelector('input[name="writing-model"]:checked').value;
            config.writing_model_name = writingModelValue;

            if (writingModelValue === 'custom') {
                config.writing_custom_type = document.querySelector('input[name="writing-custom-type"]:checked').value;

                if (config.writing_custom_type === 'ollama') {
                    config.writing_custom_ollama_model = document.getElementById('writing-ollama-model-select').value;
                } else {
                    config.writing_custom_online_model = document.getElementById('writing-online-model-name').value;
                }
            }

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
                    const analysisModelDisplay = document.querySelector('.model-info:nth-child(1) .model-value');
                    const writingModelDisplay = document.querySelector('.model-info:nth-child(2) .model-value');

                    if (analysisModelDisplay) {
                        analysisModelDisplay.textContent = config.analysis_model_name;
                    }

                    if (writingModelDisplay) {
                        writingModelDisplay.textContent = config.writing_model_name;
                    }

                    alert('API配置已保存');
                } else {
                    alert('保存API配置失败: ' + data.error);
                }
            })
            .catch(error => {
                alert('保存API配置出错: ' + error);
            });
        });
    }

    // API测试
    const testApiBtn = document.getElementById('test-api-btn');

    if (testApiBtn) {
        testApiBtn.addEventListener('click', function() {
            const testMessage = document.getElementById('test-message').value;
            const testResult = document.getElementById('test-result');

            if (!testMessage) {
                alert('请输入测试消息');
                return;
            }

            // 显示加载状态
            this.disabled = true;
            this.textContent = '测试中...';
            testResult.style.display = 'block';
            testResult.textContent = '正在连接API...';

            // 发送测试请求
            fetch('/api/test_api', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: testMessage
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    testResult.textContent = '测试成功！响应: ' + data.response;
                } else {
                    testResult.textContent = '测试失败: ' + data.error;
                }
            })
            .catch(error => {
                testResult.textContent = '测试出错: ' + error;
            })
            .finally(() => {
                // 恢复按钮状态
                this.disabled = false;
                this.textContent = '测试连接';
            });
        });
    }

    // 设置表单提交
    const settingsForm = document.getElementById('settings-form');

    if (settingsForm) {
        // 更新滑块值显示
        const temperatureSlider = document.getElementById('temperature');
        const temperatureValue = document.getElementById('temperature-value');
        const topPSlider = document.getElementById('top-p');
        const topPValue = document.getElementById('top-p-value');
        const typingSpeedSlider = document.getElementById('typing-speed');
        const typingSpeedValue = document.getElementById('typing-speed-value');

        if (temperatureSlider && temperatureValue) {
            temperatureSlider.addEventListener('input', function() {
                temperatureValue.textContent = this.value;
            });
        }

        if (topPSlider && topPValue) {
            topPSlider.addEventListener('input', function() {
                topPValue.textContent = this.value;
            });
        }

        if (typingSpeedSlider && typingSpeedValue) {
            typingSpeedSlider.addEventListener('input', function() {
                typingSpeedValue.textContent = this.value;
            });
        }

        // 提交设置
        settingsForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const settings = {
                temperature: parseFloat(document.getElementById('temperature').value),
                top_p: parseFloat(document.getElementById('top-p').value),
                max_tokens: parseInt(document.getElementById('max-tokens').value),
                show_typing_animation: document.getElementById('show-typing-animation').checked,
                typing_speed: parseInt(document.getElementById('typing-speed').value),
                enable_keyboard_shortcuts: document.getElementById('enable-keyboard-shortcuts').checked
            };

            // 发送设置到服务器
            fetch('/update_settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(settings)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('设置已保存');
                } else {
                    alert('保存设置失败');
                }
            })
            .catch(error => {
                alert('保存设置出错: ' + error);
            });
        });
    }

    // 重置应用
    const resetAppBtn = document.getElementById('reset-app-btn');

    if (resetAppBtn) {
        resetAppBtn.addEventListener('click', function() {
            if (confirm('确定要重置应用吗？这将清除当前的小说和叙事状态。')) {
                fetch('/reset_journey', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('应用已重置');
                        window.location.reload();
                    } else {
                        alert('重置应用失败');
                    }
                })
                .catch(error => {
                    alert('重置应用出错: ' + error);
                });
            }
        });
    }

    // 小说上传表单提交
    const novelUploadForm = document.getElementById('novel-upload-form');

    if (novelUploadForm) {
        novelUploadForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const novelFile = document.getElementById('novel-file').files[0];
            const novelTitle = document.getElementById('novel-title').value;

            if (!novelFile) {
                alert('请选择小说文件');
                return;
            }

            // 检查文件类型
            if (!novelFile.name.endsWith('.txt')) {
                alert('只支持TXT格式的文件');
                return;
            }

            // 显示处理中卡片
            document.getElementById('processing-card').style.display = 'flex';

            // 创建FormData对象
            const formData = new FormData();
            formData.append('novel_file', novelFile);
            formData.append('novel_title', novelTitle);

            // 发送上传请求
            fetch('/upload_novel', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 隐藏处理中卡片
                    document.getElementById('processing-card').style.display = 'none';
                    // 显示初始化叙事卡片
                    document.getElementById('initializing-narrative-card').style.display = 'flex';
                } else {
                    // 隐藏处理中卡片
                    document.getElementById('processing-card').style.display = 'none';
                    alert('处理小说失败: ' + data.error);
                }
            })
            .catch(error => {
                // 隐藏处理中卡片
                document.getElementById('processing-card').style.display = 'none';
                alert('上传小说出错: ' + error);
            });
        });
    }

    // 开始叙事按钮
    const startNarrativeBtn = document.getElementById('start-narrative-btn');

    if (startNarrativeBtn) {
        startNarrativeBtn.addEventListener('click', function() {
            // 显示加载状态
            this.disabled = true;
            this.textContent = '初始化中...';

            // 发送开始叙事请求
            fetch('/start_narrative', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 隐藏初始化叙事卡片
                    document.getElementById('initializing-narrative-card').style.display = 'none';
                    // 显示叙事卡片
                    document.getElementById('narrative-card').style.display = 'flex';
                    
                    // 添加初始叙事到历史
                    const narrativeHistory = document.getElementById('narrative-history');
                    const messageContainer = document.createElement('div');
                    messageContainer.className = 'message-container ai-message';
                    messageContainer.innerHTML = `<strong>系统:</strong><p>${data.initial_narrative}</p>`;
                    narrativeHistory.appendChild(messageContainer);
                    
                    // 滚动到底部
                    narrativeHistory.scrollTop = narrativeHistory.scrollHeight;
                } else {
                    alert('初始化叙事失败: ' + data.error);
                    // 恢复按钮状态
                    this.disabled = false;
                    this.textContent = '开始旅程';
                }
            })
            .catch(error => {
                alert('初始化叙事出错: ' + error);
                // 恢复按钮状态
                this.disabled = false;
                this.textContent = '开始旅程';
            });
        });
    }

    // 发送行动按钮
    const sendActionBtn = document.getElementById('send-action-btn');

    if (sendActionBtn) {
        sendActionBtn.addEventListener('click', function() {
            const userAction = document.getElementById('user-action').value;

            if (!userAction) {
                alert('请输入您的行动');
                return;
            }

            // 显示加载状态
            this.disabled = true;
            this.textContent = '处理中...';

            // 添加用户行动到历史
            const narrativeHistory = document.getElementById('narrative-history');
            const userMessageContainer = document.createElement('div');
            userMessageContainer.className = 'message-container user-message';
            userMessageContainer.innerHTML = `<strong>用户:</strong><p>${userAction}</p>`;
            narrativeHistory.appendChild(userMessageContainer);
            
            // 滚动到底部
            narrativeHistory.scrollTop = narrativeHistory.scrollHeight;

            // 清空输入框
            document.getElementById('user-action').value = '';

            // 发送处理行动请求
            fetch('/process_action', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    action: userAction
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 添加系统响应到历史
                    const aiMessageContainer = document.createElement('div');
                    aiMessageContainer.className = 'message-container ai-message';
                    aiMessageContainer.innerHTML = `<strong>系统:</strong><p>${data.response}</p>`;
                    narrativeHistory.appendChild(aiMessageContainer);
                    
                    // 滚动到底部
                    narrativeHistory.scrollTop = narrativeHistory.scrollHeight;
                } else {
                    alert('处理行动失败: ' + data.error);
                }
            })
            .catch(error => {
                alert('处理行动出错: ' + error);
            })
            .finally(() => {
                // 恢复按钮状态
                this.disabled = false;
                this.textContent = '发送';
            });
        });
    }

    // 保存游戏按钮
    const saveGameBtn = document.getElementById('save-game-btn');

    if (saveGameBtn) {
        saveGameBtn.addEventListener('click', function() {
            // 显示加载状态
            this.disabled = true;
            this.textContent = '保存中...';

            // 发送保存游戏请求
            fetch('/save_game', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('游戏已保存');
                } else {
                    alert('保存游戏失败: ' + data.error);
                }
            })
            .catch(error => {
                alert('保存游戏出错: ' + error);
            })
            .finally(() => {
                // 恢复按钮状态
                this.disabled = false;
                this.textContent = '保存游戏';
            });
        });
    }

    // 关闭叙事按钮
    const closeNarrativeBtn = document.getElementById('close-narrative-btn');

    if (closeNarrativeBtn) {
        closeNarrativeBtn.addEventListener('click', function() {
            // 隐藏叙事卡片
            document.getElementById('narrative-card').style.display = 'none';
        });
    }

    // 加载历史对话
    document.querySelectorAll('.load-chat-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const filePath = this.getAttribute('data-path');

            if (!filePath) {
                alert('历史对话文件路径无效');
                return;
            }

            // 显示加载状态
            this.disabled = true;
            this.textContent = '加载中...';

            // 发送加载历史对话请求
            fetch('/api/history/load', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_path: filePath
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 切换到主页
                    document.querySelector('.nav-item[data-section="home"]').click();
                    
                    // 显示初始化叙事卡片
                    document.getElementById('initializing-narrative-card').style.display = 'flex';
                } else {
                    alert('加载历史对话失败: ' + data.error);
                }
            })
            .catch(error => {
                alert('加载历史对话出错: ' + error);
            })
            .finally(() => {
                // 恢复按钮状态
                this.disabled = false;
                this.textContent = '加载';
            });
        });
    });

    // 删除历史对话
    document.querySelectorAll('.delete-chat-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const filePath = this.getAttribute('data-path');

            if (!filePath) {
                alert('历史对话文件路径无效');
                return;
            }

            if (confirm('确定要删除这个历史对话吗？')) {
                // 显示加载状态
                this.disabled = true;
                this.textContent = '删除中...';

                // 发送删除历史对话请求
                fetch('/api/history/delete', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        file_path: filePath
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // 移除对应的历史对话项
                        const chatItem = this.closest('.chat-history-item');
                        if (chatItem) {
                            chatItem.remove();
                        }
                        
                        // 如果没有历史对话了，显示空状态
                        if (document.querySelectorAll('.chat-history-item').length === 0) {
                            const emptyState = document.createElement('div');
                            emptyState.className = 'empty-state';
                            emptyState.innerHTML = '<p>暂无历史对话记录</p>';
                            document.querySelector('.chat-history-list').appendChild(emptyState);
                        }
                    } else {
                        alert('删除历史对话失败: ' + data.error);
                    }
                })
                .catch(error => {
                    alert('删除历史对话出错: ' + error);
                })
                .finally(() => {
                    // 恢复按钮状态
                    this.disabled = false;
                    this.textContent = '删除';
                });
            }
        });
    });
});
