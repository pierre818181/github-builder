import runpod
import subprocess
import os
import requests
import tarfile
import io
import logging

import re

def build_image(job):
    job_input = job["input"]
    dockerfile_path = job_input["dockerfile_path"]
    build_id = job_input["build_id"]
    cloudflare_destination = job_input["cloudflare_destination"]
    github_repo = job_input["github_repo"]
    github_repo = github_repo.replace(".git", "")
    auth_token = job_input["auth_token"]
    ref = job_input["ref"]
    jwt_token = job_input["jwt_token"]
    username_registry = job_input["username_registry"]
    refresh_worker = job_input.get("refresh_worker", "true")
    project_id = job_input["project_id"]
    refresh_worker_flag = True
    if refresh_worker == "false":
        refresh_worker_flag = False
    print(job_input)

    return_payload = {
        "refresh_worker": refresh_worker_flag,
        "token": jwt_token,
        "status": "succeeded",
        "build_id": build_id,
        "image_name": cloudflare_destination
    }

    envs = os.environ.copy()
    bun_bin_dir = os.path.expanduser("~/.bun/bin")    
    envs["DEPOT_INSTALL_DIR"] = "/root/.depot/bin"
    envs["PATH"]=f"{bun_bin_dir}:$DEPOT_INSTALL_DIR:$PATH"

    logging.info(f"Downloading {github_repo} at {ref}")
    api_url = f"https://api.github.com/repos/{github_repo.split('/')[-2]}/{github_repo.split('/')[-1]}/tarball/{ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {auth_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = requests.get(api_url, headers=headers, stream=True)
        response.raise_for_status()
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload

    logging.info(f"Extracting {github_repo} at {ref}")
    temp_dir = f"/app/{build_id}/temp"
    try:
        os.makedirs(temp_dir, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            tar.extractall(path=temp_dir)
        extracted_dir = next(os.walk(temp_dir))[1][0]
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload
    
    logging.info("Creating cache directory")
    try:
        subprocess.run("mkdir -p /app/{}/cache".format(build_id), shell=True, env=envs, check=True)
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload

    repo_dir = "/app/{}/temp/{}".format(build_id, extracted_dir)
    try: 
        subprocess.run("depot build -t {} {} --file {} . --load --project {}".format(
            cloudflare_destination, 
            repo_dir, 
            dockerfile_path, 
            project_id))
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload

    logging.info("Installing dependencies")
    envs["USERNAME_REGISTRY"] = username_registry
    envs["UUID"] = build_id
    envs["REGISTRY_JWT_TOKEN"] = jwt_token
    try:
        subprocess.run("bun install", cwd="/app/serverless-registry/push", env=envs, shell=True, executable="/bin/bash")
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload

    logging.info("Pushing image to registry")
    run_command = "bun run index.ts {}".format(cloudflare_destination)
    try:
        subprocess.run(run_command, cwd="/app/serverless-registry/push", env=envs, shell=True, check=True, executable="/bin/bash")
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload
    
    logging.info(f"Cleaning up")
    try:
        subprocess.run("rm -rf /app/{}".format(build_id), shell=True, env=envs, check=True)
    except subprocess.CalledProcessError as e:
        error_msg = str(e.stderr)
        logging.error("Something went wrong while downloading the repo: {}".format(str(error_msg)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e) + error_msg
        return return_payload
    except Exception as e:
        logging.error("Something went wrong while downloading the repo: {}".format(str(e)))
        return_payload["status"] = "failed"
        return_payload["error_msg"] = str(e)
        return return_payload

    return return_payload

runpod.serverless.start({"handler": build_image})