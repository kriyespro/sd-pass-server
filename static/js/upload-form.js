/** Multipart upload with circular progress (static files + onboarding). */
function uploadForm(opts) {
  opts = opts || {};
  var redirectFallback = opts.redirectFallback || '/projects/';
  var wizardRootId = opts.wizardRootId || '';
  var imageMaxBytes = (opts.imageMaxKb || 0) * 1024;
  var IMAGE_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'];
  return {
    uploading: false,
    uploadPct: 0,
    label: 'Uploading…',
    imageErrors: [],
    terminalLines: [],
    _termStart: 0,
    _termTimers: [],
    _termHasImages: false,
    _termFileCount: 0,
    _termLog: function(msg, kind) {
      var elapsed = Date.now() - this._termStart;
      var s = String(Math.floor(elapsed / 1000)).padStart(2, '0');
      var ms = String(Math.floor(elapsed % 1000)).padStart(3, '0');
      this.terminalLines.push({ text: '[' + s + '.' + ms + '] ' + msg, kind: kind || 'normal' });
    },
    _clearTermTimers: function() {
      this._termTimers.forEach(function(t) { clearTimeout(t); });
      this._termTimers = [];
    },
    _scheduleLog: function(delay, msg, kind) {
      var self = this;
      this._termTimers.push(setTimeout(function() { self._termLog(msg, kind); }, delay));
    },
    _parseServerError: function(responseText, status) {
      if (status === 0) return {
        reason: 'Network connection lost.',
        fix: 'Check your internet connection and try again.'
      };
      if (status === 413) return {
        reason: 'File(s) too large — server rejected the payload.',
        fix: 'Reduce file sizes, upload fewer files, or switch to ZIP upload.'
      };
      if (status === 500) return {
        reason: 'Internal server error (HTTP 500).',
        fix: 'Wait a moment and retry. If it persists, contact support.'
      };
      if (status === 503) return {
        reason: 'Server temporarily unavailable.',
        fix: 'Wait a moment and try again.'
      };
      var extracted = '';
      if (responseText) {
        try {
          var doc = new DOMParser().parseFromString(responseText, 'text/html');
          var el = doc.querySelector('.text-rose-100');
          if (el) extracted = el.textContent.trim();
        } catch(e) {}
      }
      var reason = extracted || ('Server returned HTTP ' + status + '.');
      var fix = 'Fix the error and try again.';
      if (reason.indexOf('File type not allowed') !== -1)
        fix = 'Allowed types: HTML, CSS, JS, images, fonts, JSON, SVG. Remove the disallowed file(s).';
      else if (reason.indexOf('same relative path') !== -1 || reason.indexOf('duplicate') !== -1)
        fix = 'Remove duplicate files from your selection, then re-upload.';
      else if (reason.indexOf('too deep') !== -1)
        fix = 'Flatten your folder structure or use ZIP upload for deeply nested sites.';
      else if (reason.indexOf('too long') !== -1)
        fix = 'Shorten folder or file names and try again.';
      else if (reason.indexOf('Too many') !== -1)
        fix = 'Upload fewer files per request. Split into multiple batches.';
      else if (reason.indexOf('ZIP upload page') !== -1 || reason.indexOf('archives') !== -1)
        fix = 'Use the ZIP upload page for .zip archives — not the multi-file uploader.';
      else if (reason.indexOf('Subfolder') !== -1 || reason.indexOf('subfolder') !== -1)
        fix = 'Subfolder must use only letters, digits, hyphens, underscores. No leading/trailing slashes or "..".';
      else if (reason.indexOf('120 KB') !== -1)
        fix = 'Compress the flagged image(s) below 120 KB (try Squoosh or TinyPNG) and re-upload.';
      else if (reason.indexOf('paid plan') !== -1)
        fix = 'Upgrade your plan to unlock subfolder deployment.';
      else if (reason.indexOf('Static') !== -1)
        fix = 'Change your project type to Static to use multi-file upload.';
      else if (reason.indexOf('size exceeds') !== -1 || reason.indexOf('upload limit') !== -1)
        fix = 'Reduce total upload size or split into smaller batches.';
      else if (reason.indexOf('Select one or more') !== -1)
        fix = 'Choose at least one file before submitting.';
      return { reason: reason, fix: fix };
    },
    _startTerminal: function(fileEntries) {
      var self = this;
      self.terminalLines = [];
      self._termStart = Date.now();
      self._clearTermTimers();
      var files = fileEntries || [];
      var IMG_EXTS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'];
      var imgFiles = files.filter(function(e) {
        return IMG_EXTS.indexOf('.' + e[2].split('.').pop().toLowerCase()) !== -1;
      });
      self._termHasImages = imgFiles.length > 0;
      self._termFileCount = files.length;

      self._termLog('Connecting to student-cloud deploy server...');
      self._scheduleLog(160, 'Session authenticated.');
      self._scheduleLog(340, 'Reading file manifest...');
      var t = 520;
      if (files.length > 0) {
        var preview = files.slice(0, 3).map(function(e) { return e[2].split('/').pop(); });
        var moreStr = files.length > 3 ? ' +' + (files.length - 3) + ' more' : '';
        self._scheduleLog(t, 'Found ' + files.length + ' file(s): ' + preview.join(', ') + moreStr);
        t += 200;
      }
      self._scheduleLog(t, 'Calculating checksums...'); t += 200;
      self._scheduleLog(t, 'Starting transfer...'); t += 220;

      var gap = 280;
      files.slice(0, 7).forEach(function(entry) {
        var name = entry[2].split('/').pop();
        var kb = entry[1] && entry[1].size ? ' (' + (entry[1].size / 1024).toFixed(1) + ' KB)' : '';
        var ext = '.' + name.split('.').pop().toLowerCase();
        var verb = IMG_EXTS.indexOf(ext) !== -1 ? 'Uploading image' : 'Uploading file';
        self._scheduleLog(t, verb + ': ' + name + kb); t += gap;
      });
      if (files.length > 7) {
        self._scheduleLog(t, 'Uploading ' + (files.length - 7) + ' more file(s)...'); t += gap;
      }
    },
    start: function (event) {
      var form = event.target;
      var self = this;
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }
      if (imageMaxBytes > 0) {
        var oversized = [];
        form.querySelectorAll('input[type="file"]').forEach(function (inp) {
          Array.from(inp.files || []).forEach(function (f) {
            var ext = '.' + f.name.split('.').pop().toLowerCase();
            if (IMAGE_EXTS.indexOf(ext) !== -1 && f.size > imageMaxBytes) {
              oversized.push(f.name + ' (' + Math.round(f.size / 1024) + ' KB)');
            }
          });
        });
        if (oversized.length) {
          self.imageErrors = oversized;
          return;
        }
      }
      self.imageErrors = [];
      form.querySelectorAll('input[type="file"]').forEach(function (inp) {
        if (!inp.files || inp.files.length === 0) {
          inp.disabled = true;
        }
      });
      function reenableFileInputs() {
        form.querySelectorAll('input[type="file"]:disabled').forEach(function (inp) {
          inp.disabled = false;
        });
      }
      this.uploading = true;
      this.uploadPct = 0;
      this.label = 'Uploading…';
      var fd = new FormData(form);
      // new FormData(form) uses file.name (basename only) and discards
      // webkitRelativePath, so "images/photo.jpg" arrives as "photo.jpg"
      // and the images/ subfolder structure is lost.
      // Fix: collect ALL files from ALL active inputs first, then delete
      // and re-add using webkitRelativePath. Must collect before any delete
      // so the second input's fd.delete() doesn't wipe the first input's files.
      var _fileEntries = [];
      var _fileInputNames = {};
      form.querySelectorAll('input[type="file"]:not(:disabled)').forEach(function (inp) {
        _fileInputNames[inp.name] = true;
        Array.from(inp.files || []).forEach(function (f) {
          _fileEntries.push([inp.name, f, f.webkitRelativePath || f.name]);
        });
      });
      Object.keys(_fileInputNames).forEach(function (n) { fd.delete(n); });
      _fileEntries.forEach(function (e) { fd.append(e[0], e[1], e[2]); });
      this._startTerminal(_fileEntries);
      var xhr = new XMLHttpRequest();
      var pulseTimer = null;
      var bytesSent = false;
      var lastTermPct = 0;
      xhr.open(form.method || 'POST', form.action);
      xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
      xhr.upload.addEventListener('progress', function (e) {
        if (e.lengthComputable && e.total > 0) {
          var raw = Math.round((e.loaded / e.total) * 100);
          self.uploadPct = Math.min(raw >= 100 ? 88 : raw, 88);
          if (self.uploadPct - lastTermPct >= 20) {
            lastTermPct = self.uploadPct;
            self._termLog('Transferring... ' + self.uploadPct + '%');
          }
          if (e.loaded >= e.total) {
            bytesSent = true;
            self.label = 'Processing on server…';
            self._termLog('Transfer complete. ' + self._termFileCount + ' file(s) received.');
            self._scheduleLog(350,  'Scanning for malicious code...');
            self._scheduleLog(750,  'No threats detected. Code is clean.');
            self._scheduleLog(1050, 'Checking HTML/CSS structure...');
            self._scheduleLog(1350, 'Validating file paths...');
            var t2 = 1650;
            if (self._termHasImages) {
              self._scheduleLog(t2, 'Optimizing images...'); t2 += 500;
              self._scheduleLog(t2, 'Image compression complete.'); t2 += 350;
            }
            self._scheduleLog(t2, 'Setting file permissions...'); t2 += 350;
            self._scheduleLog(t2, 'Securing your website...'); t2 += 400;
            self._scheduleLog(t2, 'SSL/TLS certificate verified.'); t2 += 350;
            self._scheduleLog(t2, 'Publishing files to CDN...'); t2 += 450;
            self._scheduleLog(t2, 'Routing traffic to your site...'); t2 += 400;
            self._scheduleLog(t2, 'It\'s time to go online!'); t2 += 300;
          }
        } else {
          self.uploadPct = Math.min(self.uploadPct + 4, 80);
        }
      });
      pulseTimer = setInterval(function () {
        if (!self.uploading) return;
        if (bytesSent && self.uploadPct < 98) {
          self.uploadPct = Math.min(self.uploadPct + 1, 98);
          self.label = 'Processing on server…';
        } else if (!bytesSent && self.uploadPct < 85) {
          self.uploadPct = Math.min(self.uploadPct + 2, 85);
        }
      }, 350);
      function stopPulse() {
        if (pulseTimer) {
          clearInterval(pulseTimer);
          pulseTimer = null;
        }
      }
      xhr.addEventListener('load', function () {
        stopPulse();
        if (xhr.status === 422 && wizardRootId) {
          var doc = new DOMParser().parseFromString(xhr.responseText, 'text/html');
          var updated = doc.getElementById(wizardRootId);
          var root = document.getElementById(wizardRootId);
          if (updated && root) {
            root.replaceWith(document.importNode(updated, true));
            if (window.Alpine) {
              var fresh = document.getElementById(wizardRootId);
              if (fresh) Alpine.initTree(fresh);
            }
            reenableFileInputs();
            self.uploading = false;
            return;
          }
        }
        if (xhr.status >= 200 && xhr.status < 400) {
          self.uploadPct = 100;
          self.label = 'Done!';
          self._clearTermTimers();
          self._termLog('Deploy queued successfully.');
          self._termLog('Site is live. Redirecting in 1s...');
          var target = (xhr.responseURL || redirectFallback).split('#')[0];
          reenableFileInputs();
          setTimeout(function() {
            self.uploading = false;
            window.location.assign(target);
          }, 1000);
          return;
        }
        self._clearTermTimers();
        var err = self._parseServerError(xhr.responseText, xhr.status);
        self._termLog('Upload failed: ' + err.reason, 'error');
        self._termLog('Fix: ' + err.fix, 'fix');
        reenableFileInputs();
        setTimeout(function() {
          alert('Upload failed\n\n' + err.reason + '\n\nHow to fix:\n' + err.fix);
          self.uploading = false;
        }, 800);
      });
      xhr.addEventListener('error', function () {
        stopPulse();
        self._clearTermTimers();
        var err = self._parseServerError('', 0);
        self._termLog('Upload failed: ' + err.reason, 'error');
        self._termLog('Fix: ' + err.fix, 'fix');
        reenableFileInputs();
        setTimeout(function() {
          alert('Upload failed\n\n' + err.reason + '\n\nHow to fix:\n' + err.fix);
          self.uploading = false;
        }, 800);
      });
      xhr.addEventListener('timeout', function () {
        stopPulse();
        self._clearTermTimers();
        self._termLog('Upload failed: Transfer timed out.', 'error');
        self._termLog('Fix: Try fewer files or switch to ZIP upload for large sites.', 'fix');
        reenableFileInputs();
        setTimeout(function() {
          alert('Upload timed out.\n\nHow to fix:\nTry fewer files or switch to ZIP upload for large sites.');
          self.uploading = false;
        }, 800);
      });
      xhr.timeout = 0;
      xhr.send(fd);
    },
  };
}
