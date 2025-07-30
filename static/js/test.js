document.addEventListener('DOMContentLoaded', function() {
    const timerElement = document.getElementById('timer');
    const form = document.getElementById('testForm');
    const submitBtn = document.getElementById('submitBtn');
    const submittedOverlay = document.getElementById('submittedOverlay');
    const webcamPrompt = document.getElementById('webcamPrompt');
    const webcamError = document.getElementById('webcamError');
    const retryWebcam = document.getElementById('retryWebcam');
    const testContainer = document.getElementById('testContainer');
    const videoElement = document.getElementById('test-video');
    let timeLeft = (window.TEST_DURATION || 30) * 60;
    let isSubmitted = false;
    let timerInterval;
    let stream;
    let mediaRecorder;
    let recordedChunks = [];
    let videoUploadPromise = null;

    let tabSwitchCount = 0;
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            tabSwitchCount++;
            fetch('/tab-switch', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ count: tabSwitchCount, timestamp: new Date().toISOString() })
            });
        }
    });

    // Start MediaRecorder
    function startRecording() {
        if (MediaRecorder.isTypeSupported('video/webm')) {
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
            recordedChunks = [];
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    recordedChunks.push(event.data);
                }
            };
            mediaRecorder.onstop = async () => {
                const blob = new Blob(recordedChunks, { type: 'video/webm' });
                const formData = new FormData();
                formData.append('video', blob, `candidate${window.CANDIDATE_ID}attempt${window.ATTEMPT_NUMBER}.webm`);
                formData.append('candidate_id', window.CANDIDATE_ID);
                try {
                    videoUploadPromise = fetch('/upload-video', {
                        method: 'POST',
                        body: formData
                    }).then(response => response.json()).then(data => {
                        console.log('Video upload response:', data.message);
                        return data;
                    }).catch(error => {
                        console.error('Error uploading video to S3:', error);
                        return null;
                    });
                    await videoUploadPromise;
                } catch (error) {
                    console.error('Error uploading video to S3:', error);
                }
            };
            mediaRecorder.start();
            console.log('Video recording started');
        } else {
            console.error('MediaRecorder: video/webm not supported');
        }
    }

    // Stop MediaRecorder and webcam
    function stopAll() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        videoElement.srcObject = null;
    }

    // Start webcam and recording
    async function startWebcam() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            videoElement.srcObject = stream;
            console.log('Webcam stream started for candidate {{ candidate_id }}');
            startRecording();
            webcamPrompt.style.display = 'none';
            testContainer.classList.remove('hidden');
            form.classList.remove('hidden');
            timerElement.style.display = 'block';
            updateTimer();
        } catch (err) {
            console.error('Error accessing webcam:', err.name, err.message);
            webcamError.textContent = `Webcam error: ${err.message}`;
            webcamError.style.display = 'block';
            retryWebcam.style.display = 'block';
        }
    }

    retryWebcam.addEventListener('click', startWebcam);
    startWebcam();

    function updateTimer() {
        const minutes = Math.floor(timeLeft / 60);
        const seconds = timeLeft % 60;
        timerElement.textContent = `Time Remaining: ${minutes}:${seconds.toString().padStart(2, '0')}`;
        if (timeLeft <= 300) timerElement.classList.add('danger');
        else if (timeLeft <= 600) timerElement.classList.add('warning');
        if (timeLeft <= 0 && !isSubmitted) {
            isSubmitted = true;
            form.classList.add('form-disabled');
            submitBtn.disabled = true;
            submittedOverlay.style.display = 'flex';
            stopAll();
            setTimeout(() => form.submit(), 3000);
        } else if (!isSubmitted) {
            timeLeft--;
            timerInterval = setTimeout(updateTimer, 1000);
        }
    }

    window.addEventListener('beforeunload', function(e) {
        if (timeLeft > 0 && !isSubmitted) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    const inputs = form.querySelectorAll('input[type="radio"]');
    // Get total questions from a JS variable, not a Jinja2 string
    const totalQuestions = window.TOTAL_QUESTIONS || 0;
    const progressInfo = document.querySelector('.progress-info');
    let answeredQuestions = new Set();
    inputs.forEach(input => {
        input.addEventListener('change', function() {
            if (!isSubmitted) {
                const questionId = this.name;
                answeredQuestions.add(questionId);
                progressInfo.innerHTML = `
                    <strong>Progress: ${answeredQuestions.size}/${totalQuestions} questions answered</strong>
                `;
                // Store attended count in sessionStorage
                sessionStorage.setItem('attended_count', answeredQuestions.size);
            }
        });
    });
    // Initialize progress bar on page load
    progressInfo.innerHTML = `<strong>Progress: 0/${totalQuestions} questions answered</strong>`;
    sessionStorage.setItem('attended_count', 0);

    // Add a hidden input to store attended count
    let attendedInput = document.createElement('input');
    attendedInput.type = 'hidden';
    attendedInput.name = 'attended_count';
    attendedInput.value = 0;
    form.appendChild(attendedInput);

    // Update hidden input on change
    function updateAttendedInput() {
        attendedInput.value = answeredQuestions.size;
    }
    inputs.forEach(input => {
        input.addEventListener('change', updateAttendedInput);
    });

    // Intercept form submission to wait for video upload
    form.addEventListener('submit', async function(e) {
        updateAttendedInput();
        if (!isSubmitted) {
            isSubmitted = true;
            submittedOverlay.style.display = 'flex';
            stopAll();
            if (videoUploadPromise) {
                e.preventDefault();
                await videoUploadPromise;
                form.submit();
            }
        }
    });
}); 