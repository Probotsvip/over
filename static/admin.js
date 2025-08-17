async function makeRequest(endpoint, options = {}) {
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.append('admin_key', window.adminKey);
    
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
}

async function loadStats() {
    try {
        const stats = await makeRequest('/api/admin/stats');
        
        document.getElementById('totalKeys').textContent = stats.total_keys;
        document.getElementById('totalRequests').textContent = stats.total_requests.toLocaleString();
        document.getElementById('activeKeys').textContent = stats.total_keys; // For now, assume all are active
        
        // Load recent logs
        const logsTable = document.getElementById('logsTable');
        if (stats.recent_logs && stats.recent_logs.length > 0) {
            logsTable.innerHTML = stats.recent_logs.map(log => `
                <tr>
                    <td>${new Date(log.timestamp).toLocaleTimeString()}</td>
                    <td><code>${log.endpoint}</code></td>
                    <td class="text-truncate" style="max-width: 150px;" title="${log.query}">${log.query}</td>
                    <td><small>${log.ip_address}</small></td>
                </tr>
            `).join('');
        } else {
            logsTable.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No recent activity</td></tr>';
        }
    } catch (error) {
        console.error('Error loading stats:', error);
        showError('Failed to load statistics');
    }
}

async function loadKeys() {
    try {
        const keys = await makeRequest('/api/admin/keys');
        
        const keysTable = document.getElementById('keysTable');
        if (keys && keys.length > 0) {
            keysTable.innerHTML = keys.map(key => {
                // Handle different data formats from different API keys
                const keyId = key.key || key.api_key || 'unknown';
                const keyName = key.name || key.owner || 'Unnamed Key';
                const isAdmin = key.is_admin || false;
                const dailyLimit = key.daily_limit || key.daily_usage || 1000;
                const count = key.count || key.total_requests || key.daily_requests || 0;
                
                return `
                <tr>
                    <td>
                        <strong>${keyName}</strong>
                        ${isAdmin ? '<span class="badge bg-warning text-dark ms-1">Admin</span>' : ''}
                    </td>
                    <td>
                        <code class="small">${keyId.substring(0, 16)}...</code>
                        <button class="btn btn-sm btn-outline-light ms-1" onclick="copyToClipboard('${keyId}', this)">
                            <i class="fas fa-copy"></i>
                        </button>
                    </td>
                    <td>${dailyLimit.toLocaleString()}</td>
                    <td>
                        <span class="text-${count > dailyLimit * 0.8 ? 'warning' : 'success'}">
                            ${count}
                        </span>
                    </td>
                    <td>
                        ${key.status ? 
                            `<span class="badge ${key.status === 'active' ? 'bg-success' : key.status === 'expired' ? 'bg-danger' : 'bg-warning'}">${key.status}</span>` :
                            '<span class="badge bg-success">active</span>'
                        }
                        ${key.valid_until ? 
                            `<br><small class="text-muted">${key.days_until_expiry || Math.max(0, Math.floor((new Date(key.valid_until) - new Date()) / (1000 * 60 * 60 * 24)))} days left</small>` :
                            ''
                        }
                    </td>
                    <td>
                        ${isAdmin ? 
                            '<span class="text-muted small">Protected</span>' : 
                            `<button class="btn btn-sm btn-outline-danger" onclick="deleteKey('${keyId}', '${keyName}')">
                                <i class="fas fa-trash"></i>
                            </button>`
                        }
                    </td>
                </tr>`;
            }).join('');
        } else {
            keysTable.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No API keys found</td></tr>';
        }
    } catch (error) {
        console.error('Error loading keys:', error);
        showError('Failed to load API keys');
    }
}

async function createKey(event) {
    event.preventDefault();
    
    const name = document.getElementById('keyName').value.trim();
    const dailyLimit = parseInt(document.getElementById('dailyLimit').value);
    const expiryDays = parseInt(document.getElementById('expiryDays').value);
    
    if (!name) {
        showError('Key name is required');
        return;
    }
    
    if (dailyLimit < 1 || dailyLimit > 10000) {
        showError('Daily limit must be between 1 and 10,000');
        return;
    }
    
    if (expiryDays < 1 || expiryDays > 3650) {
        showError('Expiry days must be between 1 and 3,650 (10 years)');
        return;
    }
    
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    
    try {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Creating...';
        
        const result = await makeRequest('/api/admin/keys', {
            method: 'POST',
            body: JSON.stringify({
                name: name,
                daily_limit: dailyLimit,
                expiry_days: expiryDays
            })
        });
        
        // Show new key
        document.getElementById('newKeyValue').textContent = result.key;
        document.getElementById('newKeyResult').style.display = 'block';
        
        // Reset form
        document.getElementById('createKeyForm').reset();
        document.getElementById('dailyLimit').value = '100';
        if (document.getElementById('expiryDays')) {
            document.getElementById('expiryDays').value = '365';
        }
        
        // Reload keys
        await loadKeys();
        await loadStats();
        
        showSuccess('API key created successfully');
        
    } catch (error) {
        console.error('Error creating key:', error);
        showError('Failed to create API key: ' + error.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

async function deleteKey(keyId, keyName) {
    if (!confirm(`Are you sure you want to delete the API key "${keyName}"?`)) {
        return;
    }
    
    try {
        await makeRequest(`/api/admin/keys/${keyId}`, {
            method: 'DELETE'
        });
        
        await loadKeys();
        await loadStats();
        showSuccess('API key deleted successfully');
        
    } catch (error) {
        console.error('Error deleting key:', error);
        showError('Failed to delete API key: ' + error.message);
    }
}

function copyToClipboard(text, button = null) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(() => {
            if (button) {
                const originalIcon = button.innerHTML;
                button.innerHTML = '<i class="fas fa-check text-success"></i>';
                setTimeout(() => {
                    button.innerHTML = originalIcon;
                }, 2000);
            }
            showSuccess('Copied to clipboard');
        }).catch(err => {
            console.error('Error copying to clipboard:', err);
            fallbackCopyToClipboard(text);
        });
    } else {
        fallbackCopyToClipboard(text);
    }
}

function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        document.execCommand('copy');
        showSuccess('Copied to clipboard');
    } catch (err) {
        console.error('Error copying to clipboard:', err);
        showError('Failed to copy to clipboard');
    }
    
    document.body.removeChild(textArea);
}

function showSuccess(message) {
    showToast(message, 'success');
}

function showError(message) {
    showToast(message, 'danger');
}

function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'position-fixed top-0 end-0 p-3';
        toastContainer.style.zIndex = '9999';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast
    const toastId = 'toast-' + Date.now();
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `toast show align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        const toastElement = document.getElementById(toastId);
        if (toastElement) {
            toastElement.remove();
        }
    }, 5000);
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('createKeyForm').addEventListener('submit', createKey);
});

// Auto-refresh functionality
let autoRefreshInterval;

function startAutoRefresh() {
    autoRefreshInterval = setInterval(() => {
        loadStats();
        loadKeys();
    }, 30000); // Refresh every 30 seconds
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
}

// Start auto-refresh when page loads
document.addEventListener('DOMContentLoaded', startAutoRefresh);

// Stop auto-refresh when page unloads
window.addEventListener('beforeunload', stopAutoRefresh);

// Handle visibility change (pause refresh when tab is hidden)
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        startAutoRefresh();
    }
});
