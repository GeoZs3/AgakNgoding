(() => {
    const script = document.currentScript;
    const endpoint = script && script.dataset.presenceUrl;
    if (!endpoint) {
        return;
    }

    const sendHeartbeat = async () => {
        try {
            const response = await fetch(endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                console.error(`Presence update failed: ${response.status}`);
            }
        } catch (error) {
            console.error("Presence update failed.", error);
        }
    };

    window.setInterval(sendHeartbeat, 60_000);
})();
