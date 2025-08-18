# Python Starter

## Steps to set up
1. Create a new repository in GitHub using this repository as a template
2. Generate Docker Hub PAT (Personal Access Token)
3. Create an [Environment in GitHub](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment#creating-an-environment) with the following secrets
   - DOCKER_USERNAME (Docker Hub username)
   - DOCKER_PASSWORD (Docker Hub PAT)
4. Create a Docker Hub repository with the same name as the GitHub repository
5. Update `assignees` in `renovate.json` with your GitHub username
6. Set up code-cove and make sure it has access to this repository
   - https://docs.codecov.com/docs/quick-start
7. Setup branch protection rules
   - Set `Enrforcment Status` to `Enabled`
   - Make sure `Target branches` set to `main` or default branch
   - Ensure these `Branch rules` are selected
     - `Restrict deletions`
     - `Require status checks to pass` with these checks
       - `Lint`
       - `Test`
     - `Block force pushes`
8. Create a PyPi `Trusted Publisher`
   - https://pypi.org/manage/account/publishing/
9. Ensure the name in `pyproject.toml` matches the name of the package on PyPi
10. Make sure the following linters are installed externally of the project
    - yamllint
    - shellcheck
    - shfmt
    - node (npx/dclint)

## TODO
- [X] Handle GitHub pre-release
- [X] Update PYTHONPATH with src folder
- [X] Add custom user to Dockerfile
- [ ] Fix Dockerfile
- [ ] Fix health check
- [ ] Fix version number
