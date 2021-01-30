from os import path
import logging

from happyai.utility import reporoot, execute
from happyai import msg

import logging.config
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': True,
})

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def check_uncommitted_changes(folder=None):
    """Checks if the given the repository at `folder` has uncommitted changes.

    Returns:
        bool: `True` if there are changes that need to be committed.
    """
    if folder is None:
        folder = reporoot

    args = ["git", "status", "."]
    log.info(f"Checking status for repository in {folder}.")
    result = execute(args, folder, printerr=False)
    has_changes = len([l for l in result["output"] 
                        if "not staged" in l or 
                        "Changes to be committed" in l or 
                        "Untracked files" in l]) > 0

    if has_changes:
        msg.warn(f"There are uncommitted changes in the repository at {folder}.")
        msg.std('\n'.join(result["output"]))
        return True

    return False


def get_branch_name(folder):
    """Gets the branch name for the repo at folder.
    """
    args = ["git", "status"]
    output = execute(args, folder, printerr=False)
    matching = [l for l in output["output"] if "On branch" in l]
    if len(matching) == 1:
        return matching[0].split()[-1]
    else:
        return None


def _git_branch(folder, branch, stash=False, sandbox=True):
    """Branches the given folder, stashing and reapplying changes if necessary.

    Args:
        stash (bool): when True, if the branch has uncommitted changes, stash them and 
            then reapply to the new branch.
    """
    if get_branch_name(folder) != branch:
        argslist = []
        if stash:
            if check_uncommitted_changes(folder):
                argslist.append(["git", "stash"])

        argslist.append((["git", "checkout", "-b", branch], _branch_error_analyzer))
        if sandbox:
            argslist.append((["git", "checkout", "-b", f"{branch}/sandbox"], _branch_error_analyzer))

        if len(argslist) == 2:
            argslist.append(["git", "stash", "apply"])

        log.debug(f"Executing branching using {argslist} in {folder}.")
        return _multi_execute(argslist, folder, f"Couldn't auto-branch the repo at {folder}.")

    else:
        log.debug(f"Repo already on branch {branch}.")
        return True


def ls_submodules(folder):
    """Lists all the submodules in the given folder.
    """
    sm_args = ["git", "submodule", "status"]
    sm_output = execute(sm_args)
    log.debug(f"Finding submodules in {folder} from process output {sm_output}")
    submodules = []
    for line in sm_output["output"]:
        parts = line.split()
        submodules.append(parts[1][3:])

    return submodules


def new_branch(branch, folder=None, stash=False, sandbox=False):
    """Creates a new branch in the given repo at `folder` as well as in any of the
    submodules.

    Args:
        folder (str): path to the repository to branch. If not specified, use `dsci-analysis`.
        branch (str): name of the new branch.
        stash (bool): when True, if the branch has uncommitted changes, stash them and 
            then reapply to the new branch.
        sandbox (bool): create a sandbox after the branching so that changes are in a 
            `branch-on-a-branch`.

    Returns:
        bool: True if it was successful.
    """
    if folder is None:
        folder = reporoot

    error = False
    if _git_branch(folder, branch, stash=stash, sandbox=sandbox):
        for submodule in ls_submodules(folder):
            subdir = path.join(folder, submodule)
            log.debug(f"Processing branching for submodule {subdir}.")
            error = not _git_branch(subdir, branch, stash=stash, sandbox=sandbox) or error
    else:
        error = True

    return not error


def is_detached(folder):
    """Determines if the specified folder is in a detached HEAD state in `git`.

    Args:
        folder (str): path to the repository to check.
    """
    args = ["git", "status"]
    output = execute(args, folder)
    return "HEAD detached at" in output["output"][0]


def _branch_error_analyzer(output):
    """Checks if there is an error in `output` for branch creation.
    """
    if len(output["error"]) > 0:
        l = output["error"][0]
        return "Switched to a new branch" not in l
    else:
        return False


def _multi_execute(argslist, subdir, error_msg):
    """Executes a series of commands in subprocesses.

    Args:
        argslist (list): of `tuple` with `(arglist, e_analyzer)` to pass to :func:`execute`.
        subdir (str): path to the folder to execute in.
        error_msg (str): error message to display if any of the commands fails.

    Returns:
        bool: `True` if the execution was successful for all steps.
    """
    for atup in argslist:
        if isinstance(atup, tuple):
            a, e_analyzer = atup
        else:
            a, e_analyzer = atup, None

        log.debug(f"Executing {a} in {subdir}")
        o = execute(a, subdir, printerr=False)
        log.debug(o)
        error = False
        if e_analyzer is not None:
            error = e_analyzer(o)
            log.debug(o, error)
        elif len(o["error"]) > 0:
            error = True

        if error:
            msg.warn(error_msg)
            return False
    else:
        return True


def _commit_printer(output):
    """Pretty-prints the commit results from :func:`_commit_repo`.
    """
    if len(output["error"]) == 0:
        o = output["output"]
        if len(o) >= 2:
            msg.okay(o[1])

        return True

    return False


def _commit_repo(folder, message):
    """Commits the changes in the repo at `folder`.
    """
    if check_uncommitted_changes(folder):
        argslist = [
                ["git", "add", "."],
                (["git", "commit", "-m", f'"{message}"'], _commit_printer)
            ]

        submodule = path.dirname(folder)
        return _multi_execute(argslist, folder, f"Could not auto-commit changes in {submodule}.")
    else:
        log.debug("No uncommitted changes; skipping commit repo.")
        return True


def commit(message, folder=None):
    """Commits the changes in each of the submodules, creating new branches if necessary.
    """
    if folder is None:
        folder = reporoot
    branch = get_branch_name(folder)

    has_error = False
    for submodule in ls_submodules(folder):
        subdir = path.join(folder, submodule)

        if not _commit_repo(subdir, message):
            # No sense trying to do anything else since we failed earlier.
            has_error = True
            continue

        if is_detached(subdir):
            # Get changes into a new branch, then checkout and merge.
            argslist = [
                ["git", "branch", "tmp"],
                # Here we are using the dsci-analysis branch name for detached heads.
                ["git", "checkout", branch],
                ["git", "merge", "tmp"],
                ["git", "branch", "-d", "tmp"]
            ]

            if not _multi_execute(argslist, subdir, f"Could not recover branch from detached head state."):
                has_error = True

    #Now that all the submodules are committed, also commit the parent repo.
    if not has_error:
        _commit_repo(folder, message)
    else:
        log.debug("Errors present in submodule repo commits; cannot commit parent repo.")
