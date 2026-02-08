# Jenkins Setup (macOS / Homebrew)

This guide covers setting up Jenkins locally on macOS using Homebrew for CI/CD with the order-service.

## Prerequisites

- **macOS** with Homebrew installed
- **Rancher Desktop** or **Lima** running (required for `nerdctl` to work)
- **GitHub account** with access to the repository

Verify Rancher Desktop is running:
```bash
nerdctl --namespace k8s.io ps
```

## Installation

```bash
brew install jenkins-lts
brew services start jenkins-lts
```

Wait a few seconds for Jenkins to initialize, then verify it's running:
```bash
brew services list | grep jenkins
# Should show: jenkins-lts started
```

## Initial Setup (First Time Only)

### Step 1: Get the Admin Password

Jenkins generates a one-time unlock password on first startup:

```bash
cat ~/.jenkins/secrets/initialAdminPassword
```

Copy this password — you'll need it in the next step.

> **Note:** This file is deleted after initial setup. If you need to reset Jenkins, delete `~/.jenkins/` and restart the service.

### Step 2: Access Jenkins UI

Open in your browser: **http://localhost:8080**

(Or http://localhost:8090 if you changed the port — see [Changing the Default Port](#changing-the-default-port))

### Step 3: Unlock Jenkins

1. Paste the password from Step 1 into the "Administrator password" field
2. Click **Continue**

### Step 4: Install Plugins

1. Select **"Install suggested plugins"**
2. Wait for plugins to download and install (this takes 2-5 minutes)

The suggested plugins include Git, Pipeline, and other essentials needed for our Jenkinsfile.

### Step 5: Create Admin User

Fill in the form:
- **Username:** `admin` (or your preference)
- **Password:** Choose a strong password
- **Full name:** Your name
- **Email:** Your email

Click **Save and Continue**.

### Step 6: Configure Jenkins URL

Keep the default URL (`http://localhost:8080/` or your custom port).

Click **Save and Finish**, then **Start using Jenkins**.

## Adding GitHub Credentials

The Jenkinsfile references credentials with ID `yaml-sprinklr-github-pat`. You need to create these.

### Step 1: Generate a GitHub Personal Access Token

1. Go to GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)**
2. Click **Generate new token (classic)**
3. Set:
   - **Note:** `jenkins-warmup-project`
   - **Expiration:** 90 days (or your preference)
   - **Scopes:** Check `repo` (full control of private repositories)
4. Click **Generate token**
5. **Copy the token immediately** — you won't see it again

### Step 2: Add Credentials to Jenkins

1. In Jenkins, go to: **Manage Jenkins** → **Credentials**
2. Click **(global)** under "Stores scoped to Jenkins"
3. Click **Add Credentials**
4. Fill in:
   - **Kind:** Username with password
   - **Scope:** Global
   - **Username:** Your GitHub username
   - **Password:** Paste the GitHub token
   - **ID:** `yaml-sprinklr-github-pat` (must match exactly)
   - **Description:** `GitHub PAT for warmup-project`
5. Click **Create**

## Changing the Default Port

Jenkins defaults to port 8080, which may conflict with other services (e.g., K8s port-forwards).

### The Gotcha

`brew services` copies the plist from Homebrew's source directory each time it starts. Editing `~/Library/LaunchAgents/homebrew.mxcl.jenkins-lts.plist` directly **does not persist** — it gets overwritten on restart.

### Correct Method

Edit the **source** plist:

```bash
brew services stop jenkins-lts

# Change port (e.g., 8080 → 8090)
sed -i '' 's/--httpPort=8080/--httpPort=8090/' /opt/homebrew/opt/jenkins-lts/homebrew.mxcl.jenkins-lts.plist

brew services start jenkins-lts
```

Verify:
```bash
grep httpPort /opt/homebrew/opt/jenkins-lts/homebrew.mxcl.jenkins-lts.plist
```

### After `brew upgrade`

A Jenkins upgrade will reset the plist. Re-apply the port change:

```bash
sed -i '' 's/--httpPort=8080/--httpPort=8090/' /opt/homebrew/opt/jenkins-lts/homebrew.mxcl.jenkins-lts.plist
brew services restart jenkins-lts
```

## Creating the Pipeline Job

### Step 1: Create New Item

1. From the Jenkins dashboard, click **New Item** (left sidebar)
2. Enter name: `order-service`
3. Select **Pipeline**
4. Click **OK**

### Step 2: Configure Pipeline

Scroll down to the **Pipeline** section:

1. **Definition:** Select `Pipeline script from SCM`
2. **SCM:** Select `Git`
3. **Repository URL:** `https://github.com/yaml-sprinklr/warmup-project-sprinklr.git`
4. **Credentials:** Select `yaml-sprinklr-github-pat` from the dropdown
5. **Branch Specifier:** `*/main`
6. **Script Path:** `Jenkinsfile`

Leave other settings as defaults.

### Step 3: Save and Run

1. Click **Save**
2. Click **Build Now** (left sidebar)
3. Watch the build progress in **Build History**
4. Click the build number → **Console Output** to see logs

### Expected Pipeline Stages

The Jenkinsfile defines these stages:

| Stage | What it does |
|-------|--------------|
| **Build** | Builds the Docker image using `nerdctl` |
| **Test** | Runs unit tests inside a container |

## Troubleshooting

### "nerdctl: not found" or "exec: nerdctl: not found"

**Cause:** Jenkins can't find the `nerdctl` binary.

**Fix:** Ensure Rancher Desktop is running and `nerdctl` is in PATH:
```bash
which nerdctl
# Should return: /usr/local/bin/nerdctl
```

If missing, add to your shell profile and restart Jenkins:
```bash
echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc
brew services restart jenkins-lts
```

### "exec: /usr/local/libexec/nerdctl/nerdctl: not found"

**Cause:** You're running Jenkins in a container. The `nerdctl` shim can't reach the Lima/Rancher VM.

**Fix:** Use Homebrew Jenkins instead of containerized Jenkins (see [Why Homebrew](#why-homebrew-instead-of-containerized-jenkins)).

### Build fails with "permission denied" on containerd socket

**Cause:** Jenkins user can't access the containerd socket.

**Fix:** Ensure the Rancher Desktop VM is running and your user has access:
```bash
# Test nerdctl manually
nerdctl --namespace k8s.io ps
```

### "Repository not found" or "Authentication failed"

**Cause:** GitHub credentials are missing or incorrect.

**Fix:**
1. Verify the credential ID is exactly `yaml-sprinklr-github-pat`
2. Check that the GitHub token hasn't expired
3. Ensure the token has `repo` scope

## Why Homebrew Instead of Containerized Jenkins?

Running Jenkins in a container (e.g., via nerdctl/Docker) creates issues when the pipeline needs to use container tools like `nerdctl`:

- The `nerdctl` binary on macOS is a **shim** that delegates to Lima/Rancher Desktop's VM
- Inside a container, this shim fails because the backing VM isn't accessible
- Error: `/usr/local/bin/nerdctl: exec: /usr/local/libexec/nerdctl/nerdctl: not found`

Homebrew Jenkins runs natively on macOS, with full access to the Lima/Rancher Desktop toolchain.

## Data Locations

| Item | Path |
|------|------|
| Jenkins home | `~/.jenkins/` |
| Jobs & builds | `~/.jenkins/jobs/` |
| Plugins | `~/.jenkins/plugins/` |
| Service plist (source) | `/opt/homebrew/opt/jenkins-lts/homebrew.mxcl.jenkins-lts.plist` |
| Service plist (runtime copy) | `~/Library/LaunchAgents/homebrew.mxcl.jenkins-lts.plist` |

## Useful Commands

```bash
# Start/stop/restart
brew services start jenkins-lts
brew services stop jenkins-lts
brew services restart jenkins-lts

# Check status
brew services list | grep jenkins

# View logs
tail -f ~/.jenkins/logs/jenkins.log

# Upgrade Jenkins
brew upgrade jenkins-lts
# Remember to re-apply port change after upgrade!
```
