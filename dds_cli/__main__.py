"""CLI for the Data Delivery System."""

####################################################################################################
# IMPORTS ################################################################################ IMPORTS #
####################################################################################################

# Standard library
import concurrent.futures
import itertools
import logging
import os
import sys

# Installed
import rich_click as click
import click_pathlib
import rich
import rich.logging
import rich.markup
import rich.progress
import rich.prompt
import questionary

# Own modules
import dds_cli
import dds_cli.account_manager
import dds_cli.unit_manager
import dds_cli.motd_manager
import dds_cli.maintenance_manager
import dds_cli.data_getter
import dds_cli.data_lister
import dds_cli.data_putter
import dds_cli.data_remover
import dds_cli.directory
import dds_cli.project_creator
import dds_cli.auth
import dds_cli.project_status
import dds_cli.user
import dds_cli.utils
from dds_cli.options import (
    email_arg,
    email_option,
    folder_option,
    num_threads_option,
    project_option,
    sort_projects_option,
    source_option,
    source_path_file_option,
    token_path_option,
    username_option,
    break_on_fail_flag,
    json_flag,
    nomail_flag,
    silent_flag,
    size_flag,
    tree_flag,
    usage_flag,
    users_flag,
)

####################################################################################################
# START LOGGING CONFIG ###################################################### START LOGGING CONFIG #
####################################################################################################

LOG = logging.getLogger()

# Configuration for rich-click output
click.rich_click.MAX_WIDTH = 100


## # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#                                                                                                  #
#                          MMMM   MMMM      AAAA      II   NNNN    NN                              #
#                          MM MM MM MM     AA  AA     II   NN NN   NN                              #
#                          MM  MMM  MM    AA    AA    II   NN  NN  NN                              #
#                          MM   M   MM   AAAAAAAAAA   II   NN   NN NN                              #
#                          MM       MM   AA      AA   II   NN    NNNN                              #
#                                                                                                  #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # ##


dds_url = dds_cli.DDSEndpoint.BASE_ENDPOINT
# Print header to STDERR
dds_cli.utils.stderr_console.print(
    "[green]     ︵",
    "\n[green] ︵ (  )   ︵",
    "\n[green](  ) ) (  (  )[/]   [bold]SciLifeLab Data Delivery System",
    "\n[green] ︶  (  ) ) ([/]    [blue][link={0}]{0}/[/link]".format(
        dds_url[: dds_url.index("/", 8)]
    ),
    f"\n[green]      ︶ (  )[/]    [dim]Version {dds_cli.__version__}",
    "\n[green]          ︶",
    highlight=False,
)

if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] != "motd"):
    motds = dds_cli.motd_manager.MotdManager.list_all_active_motds(table=False)
    if motds:
        dds_cli.utils.stderr_console.print(f"[bold]Important information:[/bold]")
        for motd in motds:
            dds_cli.utils.stderr_console.print(f"{motd['Created']} - {motd['Message']} \n")

# -- dds -- #
@click.group()
@click.option(
    "-v", "--verbose", is_flag=True, default=False, help="Print verbose output to the console."
)
@click.option("-l", "--log-file", help="Save a log to a file.", metavar="<filename>")
@click.option(
    "--no-prompt", is_flag=True, default=False, help="Run without any interactive features."
)
@token_path_option()
@click.version_option(
    version=dds_cli.__version__,
    prog_name=dds_cli.__title__,
    help="Display the version of this software.",
)
@click.help_option(
    help="List the options of any DDS subcommand and its default settings.",
)
@click.pass_context
def dds_main(click_ctx, verbose, log_file, no_prompt, token_path):
    """SciLifeLab Data Delivery System (DDS) command line interface.

    Access token is saved in a .dds_cli_token file in the home directory.

    The token is valid for 7 days. Make sure your token is valid long enough for the
    delivery to finish. To avoid that a delivery fails because of an expired token, we recommend
    reauthenticating yourself before each delivery ('dds data put' / 'get').
    """
    # Get token metadata
    username = dds_cli.user.User.get_user_name_if_logged_in(token_path=token_path)

    if username:
        dds_cli.utils.stderr_console.print(
            f"[green]Current user:[/] [red]{username}", highlight=False
        )

    if "--help" not in sys.argv:
        # Set the base logger to output DEBUG
        LOG.setLevel(logging.DEBUG)

        # Set up logs to the console
        LOG.addHandler(
            rich.logging.RichHandler(
                level=logging.DEBUG if verbose else logging.INFO,
                console=dds_cli.utils.stderr_console,
                show_time=False,
                markup=True,
                show_path=verbose,
            )
        )

        # Set up logs to a file if we asked for one
        if log_file:
            log_fh = logging.FileHandler(log_file, encoding="utf-8")
            log_fh.setLevel(logging.DEBUG)
            log_fh.setFormatter(
                logging.Formatter("[%(asctime)s] %(name)-20s [%(levelname)-7s]  %(message)s")
            )
            LOG.addHandler(log_fh)

        # Create context object
        click_ctx.obj = {"NO_PROMPT": no_prompt, "TOKEN_PATH": token_path}


# ************************************************************************************************ #
# MAIN DDS COMMANDS ************************************************************ MAIN DDS COMMANDS #
# ************************************************************************************************ #

# -- dds ls -- #
@dds_main.command(name="ls")
# Options
@project_option(required=False)
@sort_projects_option()
@folder_option(help_message="List contents of this project folder.")
@click.option(
    "--binary",
    "-b",
    required=False,
    is_flag=True,
    default=False,
    help=(
        "Use binary unit prefixes (e.g. KiB instead of KB, "
        "MiB instead of MB) for size and usage columns."
    ),
)
# Flags
@json_flag(help_message="Output in JSON format.")
@size_flag(help_message="Show size of project contents.")
@tree_flag(help_message="Display the entire project(s) directory tree.")
@usage_flag(help_message="Show the usage for available projects, in GBHours and cost.")
@users_flag(help_message="Display users associated with a project(Requires a project id).")
@click.option("--projects", "-lp", is_flag=True, help="List all project connected to your account.")
@click.pass_obj
def list_projects_and_contents(
    click_ctx, project, folder, sort, json, size, tree, usage, binary, users, projects
):
    """List the projects you have access to or the project contents.

    To list all projects, run `dds ls` without any arguments, or use the `--projects` flag.

    Specify a Project ID to list the files within a project.
    You can also follow this with a subfolder path to show files within that folder.
    """
    try:
        # List all projects if project is None and all files if project spec
        if project is None:
            with dds_cli.data_lister.DataLister(
                project=project,
                show_usage=usage,
                no_prompt=click_ctx.get("NO_PROMPT", False),
                json=json,
                token_path=click_ctx.get("TOKEN_PATH"),
                binary=binary,
            ) as lister:
                projects = lister.list_projects(sort_by=sort)
                if json:
                    dds_cli.utils.console.print_json(data=projects)
                else:
                    # If an interactive terminal, ask user if they want to view files for a project
                    if sys.stdout.isatty() and not lister.no_prompt:
                        project_ids = [p["Project ID"] for p in projects]
                        LOG.info(
                            "Would you like to view files in a specific project? "
                            "Leave blank to exit."
                        )
                        # Keep asking until we get a valid response
                        while project not in project_ids:
                            try:
                                project = questionary.autocomplete(
                                    "Project ID:",
                                    choices=project_ids,
                                    validate=lambda x: x in project_ids or x == "",
                                    style=dds_cli.dds_questionary_styles,
                                ).unsafe_ask()
                                assert project and project != ""

                            # If didn't enter anything, convert to None and exit
                            except (KeyboardInterrupt, AssertionError):
                                break

        # List all files in a project if we know a project ID
        if project:
            with dds_cli.data_lister.DataLister(
                project=project,
                tree=tree,
                no_prompt=click_ctx.get("NO_PROMPT", False),
                json=json,
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as lister:
                if json:
                    json_output = {"project_name": project}
                    if users:
                        user_list = lister.list_users()
                        json_output["users"] = user_list

                    if tree:
                        folders = lister.list_recursive(show_size=size)
                        json_output["project_files_and_directories"] = folders
                    else:
                        LOG.warning(
                            "JSON output for file listing only possible for the complete file tree."
                            " Please use the '--tree' option to view complete contens in JSON or "
                            "remove the '--json' option to list files interactively"
                        )
                    dds_cli.utils.console.print_json(data=json_output)
                else:
                    if users:
                        user_list = lister.list_users()

                    if tree:
                        folders = lister.list_recursive(show_size=size)
                    else:
                        folders = lister.list_files(folder=folder, show_size=size)

                        # If an interactive terminal, ask user if they want to view files for a proj
                        if sys.stdout.isatty() and (not lister.no_prompt) and len(folders) > 0:
                            LOG.info(
                                "Would you like to view files within a directory? "
                                "Leave blank to exit."
                            )
                            last_folder = None
                            while folder is None or folder != last_folder:
                                last_folder = folder

                                try:
                                    folder = questionary.autocomplete(
                                        "Folder:",
                                        choices=folders,
                                        validate=lambda x: x in folders or x == "",
                                        style=dds_cli.dds_questionary_styles,
                                    ).unsafe_ask()
                                    assert folder != ""
                                    assert folder is not None
                                # If didn't enter anything, convert to None and exit
                                except (KeyboardInterrupt, AssertionError):
                                    break

                                # Prepend existing file path
                                if last_folder is not None and folder is not None:
                                    folder = os.path.join(last_folder, folder)

                                # List files
                                folders = lister.list_files(folder=folder, show_size=size)

                                if len(folders) == 0:
                                    break

    except (dds_cli.exceptions.NoDataError) as err:
        LOG.warning(err)
        sys.exit(0)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


####################################################################################################
####################################################################################################
## AUTH #################################################################################### AUTH ##
####################################################################################################
####################################################################################################


@dds_main.group(name="auth", no_args_is_help=True)
@click.pass_obj
def auth_group_command(_):
    """Group command for creating and managing authenticated sessions.

    Authenticate yourself once and run multiple commands within a certain amount of time
    (currently 7 days) without specifying your user credentials.
    If you do not authenticate yourself and start a new session, you will need to provide your
    DDS username when running the other commands.

    All subcommands are usable by all user roles.
    """


# ************************************************************************************************ #
# AUTH COMMANDS ******************************************************************** AUTH COMMANDS #
# ************************************************************************************************ #


# -- dds auth login -- #
@auth_group_command.command(name="login")
@click.option(
    "--totp",
    type=str,
    default=None,
    help="2FA authentication via authentication app. Default is to use one-time authentication code via mail.",
)
@click.option(
    "--allow-group",
    is_flag=True,
    required=False,
    default=False,
    help="[Not recommended, use with care] Allow read permissions to group. Sets 640 permission instead of 600.",
)
@click.pass_obj
def login(click_ctx, totp, allow_group):
    """Start or renew an authenticated session.

    Creates or renews the authentication token stored in the '.dds_cli_token' file.

    Run this command before running the cli in a non-interactive fashion as this enables the longest
    possible session time before a password needs to be entered again.

    The permissions of tokens cannot be changed after the tokens are established.
    If you began an authenticated session without the use of the --allow-group option,
    but want to use it in a new session, use 'dds auth logout' to end the current session.
    Then use the --allow-group option and start a new session. This also applies to the reverse.
    """
    no_prompt = click_ctx.get("NO_PROMPT", False)
    if no_prompt:
        LOG.warning("The --no-prompt flag is ignored for `dds auth login`")
    try:
        with dds_cli.auth.Auth(
            token_path=click_ctx.get("TOKEN_PATH"), totp=totp, allow_group=allow_group
        ):
            # Authentication token renewed in the init method.
            LOG.info("[green] :white_check_mark: Authentication token created![/green]")
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds auth logout -- #
@auth_group_command.command(name="logout")
@click.pass_obj
def logout(click_ctx):
    """End authenticated session.

    Removes the saved authentication token by deleting the '.dds_cli_token' file.
    """
    try:
        with dds_cli.auth.Auth(
            authenticate=False, token_path=click_ctx.get("TOKEN_PATH")
        ) as authenticator:
            authenticator.logout()

    except (dds_cli.exceptions.DDSCLIException, dds_cli.exceptions.ApiRequestError) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds auth info -- #
@auth_group_command.command(name="info")
@click.pass_obj
def info(click_ctx):
    """Display information about ongoing authenticated session.

    \b
    Information displayed:
    - If the token is about to expire
    - Time of token expiration
    """
    try:
        with dds_cli.auth.Auth(
            authenticate=False, token_path=click_ctx.get("TOKEN_PATH")
        ) as authenticator:
            authenticator.check()
    except (dds_cli.exceptions.DDSCLIException, dds_cli.exceptions.ApiRequestError) as err:
        LOG.error(err)
        sys.exit(1)


# ************************************************************************************************ #
# AUTH SUB GROUPS **************************************************************** AUTH SUB GROUPS #
# ************************************************************************************************ #


# TWOFACTOR ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ TWOFACTOR #


@auth_group_command.group(name="twofactor", no_args_is_help=True)
@click.pass_obj
def twofactor_group_command(_):
    """Group command for configuring and deactivating methods of two factor authentication."""


# -- dds auth twofactor configure -- #
@twofactor_group_command.command(name="configure")
def configure():
    """Configure your preferred method of two-factor authentication."""
    try:
        LOG.info("Starting configuration of one-time authentication code method.")
        auth_method_choice: str = questionary.select(
            "Which method would you like to use?", choices=["Email", "Authenticator App", "Cancel"]
        ).ask()

        if auth_method_choice == "Cancel":
            LOG.info("Two-factor authentication method not configured.")
            sys.exit(0)
        elif auth_method_choice == "Authenticator App":
            auth_method: str = "totp"
        elif auth_method_choice == "Email":
            auth_method: str = "hotp"

        with dds_cli.auth.Auth(authenticate=True, force_renew_token=False) as authenticator:
            authenticator.twofactor(auth_method=auth_method)
    except (dds_cli.exceptions.DDSCLIException, dds_cli.exceptions.ApiResponseError) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds auth twofactor configure -- #
@twofactor_group_command.command(name="deactivate")
@username_option(
    required=True, help_message="Super Admins only: The user you wish to deactivate TOTP for."
)
@click.pass_obj
def deactivate(click_ctx, username):
    """Deactivate another users TOTP.

    Only usable by Super Admins.
    """
    try:
        with dds_cli.auth.Auth(
            token_path=click_ctx.get("TOKEN_PATH"), force_renew_token=False
        ) as authenticator:
            authenticator.deactivate(username=username)
    except (dds_cli.exceptions.DDSCLIException, dds_cli.exceptions.ApiResponseError) as err:
        LOG.error(err)
        sys.exit(1)


####################################################################################################
####################################################################################################
## USER #################################################################################### USER ##
####################################################################################################
####################################################################################################


@dds_main.group(name="user", no_args_is_help=True)
@click.pass_obj
def user_group_command(_):
    """Group command for managing user accounts, including your own."""


# ************************************************************************************************ #
# USER COMMANDS ******************************************************************** USER COMMANDS #
# ************************************************************************************************ #

# -- dds user ls -- #
# TODO: Move this to dds unit?
@user_group_command.command(name="ls")
@click.option(
    "--unit",
    "-u",
    required=False,
    type=str,
    help="Super Admins only: The unit which you wish to list the users in.",
)
@click.pass_obj
def list_users(click_ctx, unit):
    """List Unit Admins and Personnel connected to a specific unit.

    \b
    Super Admins:
        - Required to specify a public unit ID.
        - Can list users within all units.

    \b
    Unit Admins / Personnel:
        - Any unit specified with `--unit` will be ignored.
        - You can only list users connected to your specific unit.
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as lister:
            lister.list_users(unit=unit)

    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds user find -- #
# TODO: Move this to dds unit?
@user_group_command.command(name="find")
@username_option(
    required=True, help_message="Super Admins only: The username of the account you want to check."
)
@click.pass_obj
def list_users(click_ctx, username):
    """Check if a username is registered to an account in the DDS."""
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as lister:
            lister.find_user(user_to_find=username)

    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds user add -- #
@user_group_command.command(name="add", no_args_is_help=True)
# Positional args
@email_arg(required=True)
# Options
@project_option(
    required=False, help_message="Existing Project you want the user to be associated to."
)
@click.option(
    "--role",
    "-r",
    "role",
    required=True,
    type=click.Choice(
        choices=["Super Admin", "Unit Admin", "Unit Personnel", "Project Owner", "Researcher"],
        case_sensitive=False,
    ),
    help=(
        "Type of account. To include a space in the chosen role, use quotes "
        '(e.g. "Unit Personnel") or escape the space (e.g. Unit\ Personnel)'
    ),
)
@click.option(
    "--unit",
    required=False,
    help="Super Admins only: To specify which unit the user should belong to.",
)
@nomail_flag(help_message="Do not send e-mail notifications regarding project updates.")
@click.pass_obj
def add_user(click_ctx, email, role, project, unit, no_mail):
    """Invite a new user to the DDS or add an existing one to a hosted project.

    Not available for Researchers, unless they are marked as Project Owner for a specific project.

    \b
    Invite new user:
        - Email
        - Role

    \b
    Add user to project:
        - Email
        - Project ID (`dds ls`)
        - Role: Researcher / Project Owner only in this case.
        Unit Admins / Personnel are automatically added to all projects within that specific unit.
        If the user doesn't exist in the system yet, an invitation email will be sent automatically
        to that person.
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as inviter:
            inviter.add_user(email=email, role=role, project=project, no_mail=no_mail, unit=unit)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds user delete -- #
@user_group_command.command(name="delete", no_args_is_help=True)
# Positional args
@email_arg(required=False)
# Options
# Flags
@click.option(
    "--self",
    "self",
    required=False,
    is_flag=True,
    default=False,
    help="Request deletion of own account.",
)
@click.option(
    "--is-invite",
    required=False,
    is_flag=True,
    default=False,
    help="Delete an ongoing and unanswered invite.",
)
@click.pass_obj
def delete_user(click_ctx, email, self, is_invite):
    """Delete user accounts from the Data Delivery System.

    Use this command with caution. Deletion of accounts cannot be undone.

    To request the removal of your own account, use the `--self` flag without any arguments.
    An e-mail will be sent to you asking to confirm the deletion.

    If you have sufficient admin privileges, you may also delete the accounts of some other users.
    Specify the e-mail address as argument to the main command to initiate the removal process.

    Deleting a user will not delete any data.

    \b
    Super Admins: All users.
    Unit Admins: Unit Admins / Personnel. Not Researchers since they can be involved in projects
    connected to other units.
    """
    if click_ctx.get("NO_PROMPT", False):
        proceed_deletion = True
    else:
        if is_invite and self:
            LOG.error("You cannot specify both `--self` and `--is-invite. Choose one.")
            sys.exit(0)

        if not self and not email:
            LOG.error(
                "You must specify an email adress associated to the user you're requesting to delete."
            )
            sys.exit(0)

        if is_invite:
            proceed_deletion = rich.prompt.Confirm.ask(
                f"Delete invitation of {email} to Data Delivery System?"
            )
        else:
            if self:
                proceed_deletion = rich.prompt.Confirm.ask(
                    "Are you sure? Deleted accounts can't be restored!"
                )
            else:
                proceed_deletion = rich.prompt.Confirm.ask(
                    f"Delete Data Delivery System user account associated with {email}"
                )

    if proceed_deletion:
        try:
            with dds_cli.account_manager.AccountManager(
                method="delete",
                no_prompt=click_ctx.get("NO_PROMPT", False),
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as manager:
                if self and not email:
                    manager.delete_own_account()
                elif email and not self:
                    manager.delete_user(email=email, is_invite=is_invite)
                else:
                    LOG.error(
                        "You must either specify the '--self' flag "
                        "or the e-mail address of the user to be deleted"
                    )
                    sys.exit(1)

        except (
            dds_cli.exceptions.AuthenticationError,
            dds_cli.exceptions.ApiResponseError,
            dds_cli.exceptions.ApiRequestError,
            dds_cli.exceptions.DDSCLIException,
        ) as err:
            LOG.error(err)
            sys.exit(1)


# -- dds user info -- #
@user_group_command.command(name="info")
# Options
# Flags
@click.pass_obj
def get_info_user(click_ctx):
    """Display information connected to your own DDS account.

    Usable by all user roles.

    \b
    The following information should be displayed:
    - Username
    - Role
    - Name
    - Primary email
    - Associated emails (not useful yet)
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as get_info:
            get_info.get_user_info()
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds user activate -- #
@user_group_command.command(name="activate", no_args_is_help=True)
# Positional args
@email_arg(required=True)
# Options
# Flags
@click.pass_obj
def activate_user(click_ctx, email):
    """Activate/Reactivate user accounts.

    \b
    Usable only by Super Admins and Unit Admins.
    Super Admins: All users
    Unit Admins: Unit Admins / Personnel
    """
    if click_ctx.get("NO_PROMPT", False):
        pass
    else:
        proceed_activation = rich.prompt.Confirm.ask(
            f"Activate Data Delivery System user account associated with {email}?"
        )

    if proceed_activation:
        try:
            with dds_cli.account_manager.AccountManager(
                no_prompt=click_ctx.get("NO_PROMPT", False),
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as manager:
                manager.user_activation(email=email, action="reactivate")

        except (
            dds_cli.exceptions.AuthenticationError,
            dds_cli.exceptions.ApiResponseError,
            dds_cli.exceptions.ApiRequestError,
            dds_cli.exceptions.DDSCLIException,
        ) as err:
            LOG.error(err)
            sys.exit(1)


# -- dds user deactivate -- #
@user_group_command.command(name="deactivate", no_args_is_help=True)
# Positional args
@email_arg(required=True)
# Options
# Flags
@click.pass_obj
def deactivate_user(click_ctx, email):
    """Deactivate user accounts in the Data Delivery System.

    \b
    Usable only by Super Admins and Unit Admins.
    Super Admins: All users
    Unit Admins: Unit Admins / Personnel
    """
    if click_ctx.get("NO_PROMPT", False):
        pass
    else:
        proceed_deactivation = rich.prompt.Confirm.ask(
            f"Deactivate Data Delivery System user account associated with {email}?"
        )

    if proceed_deactivation:
        try:
            with dds_cli.account_manager.AccountManager(
                no_prompt=click_ctx.get("NO_PROMPT", False),
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as manager:
                manager.user_activation(email=email, action="deactivate")

        except (
            dds_cli.exceptions.AuthenticationError,
            dds_cli.exceptions.ApiResponseError,
            dds_cli.exceptions.ApiRequestError,
            dds_cli.exceptions.DDSCLIException,
        ) as err:
            LOG.error(err)
            sys.exit(1)


####################################################################################################
####################################################################################################
## PROJECT ############################################################################## PROJECT ##
####################################################################################################
####################################################################################################


@dds_main.group(name="project", no_args_is_help=True)
@click.pass_obj
def project_group_command(_):
    """Group command for creating and managing projects within the DDS."""


# ************************************************************************************************ #
# PROJECT COMMANDS ************************************************************** PROJECT COMMANDS #
# ************************************************************************************************ #


# -- dds project ls -- #
@project_group_command.command(name="ls")
# Options
@sort_projects_option()
# Flags
@usage_flag(help_message="Show the usage for available projects, in GBHours and cost.")
@json_flag(help_message="Output project list as json.")  # users, json, tree
@click.pass_context
def list_projects(ctx, json, sort, usage):
    """List all projects you have access to in the DDS.

    Calls the `dds ls` function.
    """
    ctx.invoke(list_projects_and_contents, json=json, sort=sort, usage=usage)


# -- dds project create -- #
@project_group_command.command(no_args_is_help=True)
# Options
@click.option(
    "--title",
    "-t",
    required=True,
    type=str,
    help="The title of the project.",
)
@click.option(
    "--description",
    "-d",
    required=True,
    type=str,
    help="A description of the project.",
)
@click.option(
    "--principal-investigator",
    "-pi",
    required=True,
    type=str,
    help=(
        "Email of the Principal Investigator. "
        "Note: The PI will not be added as a user in the DDS. "
        "Add the same email as the `--owner` if the PI should have an account."
    ),
)
@click.option(
    "--researcher",
    required=False,
    multiple=True,
    help="Email of a user to be added to the project as Researcher."
    + dds_cli.utils.multiple_help_text(item="researcher"),
)
# Flags
@click.option(
    "--owner",
    "owner",
    required=False,
    multiple=True,
    help="Email of user to be added to the project as Project Owner."
    + dds_cli.utils.multiple_help_text(item="project owner"),
)
@click.option(
    "--non-sensitive",
    required=False,
    is_flag=True,
    default=False,
    help=(
        "Indicate whether the project contains only non-sensitive data. "
        "NB! Currently all data is encrypted independent of whether the "
        "projects is marked as sensitive or not."
    ),
)
@click.pass_obj
def create(
    click_ctx,
    title,
    description,
    principal_investigator,
    non_sensitive,
    owner,
    researcher,
):
    """Create a project within the DDS.

    Only usable by Unit Admins / Personnel.

    To give new or existing users access to the new project, specify their emails with
    `--researcher` or `--owner`. Both of these will give the user the role Researcher, but `--owner`
    will mark the user as a Project Owner for this specific project, which will give that person
    some additional administrative rights within the project such as adding users etc.
    """
    try:
        with dds_cli.project_creator.ProjectCreator(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as creator:
            emails_roles = []
            if owner or researcher:
                email_overlap = set(owner) & set(researcher)
                if email_overlap:
                    LOG.info(
                        f"The email(s) {email_overlap} specified as both owner and researcher! "
                        "Please specify a unique role for each email."
                    )
                    sys.exit(1)
                if owner:
                    emails_roles.extend([{"email": x, "role": "Project Owner"} for x in owner])
                if researcher:
                    emails_roles.extend([{"email": x, "role": "Researcher"} for x in researcher])

            created, project_id, user_addition_messages, err = creator.create_project(
                title=title,
                description=description,
                principal_investigator=principal_investigator,
                non_sensitive=non_sensitive,
                users_to_add=emails_roles,
            )
            if created:
                dds_cli.utils.console.print(
                    f"Project created with id: {project_id}",
                )
                if user_addition_messages:
                    for msg in user_addition_messages:
                        dds_cli.utils.console.print(msg)
                    dds_cli.utils.console.print(
                        "[red]Any users with errors were not added to the project[/red]"
                    )
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# ************************************************************************************************ #
# PROJECT SUB GROUPS ********************************************************** PROJECT SUB GROUPS #
# ************************************************************************************************ #


# STATUS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ STATUS #
@project_group_command.group(name="status", no_args_is_help=True)
@click.pass_obj
def project_status(_):
    """Manage project statuses.

    Display or change the status of a project.

    Displaying the project status is available for all user roles. Changing the project status
    is limited to Unit Admins and Personnel.
    """


# -- dds project status display -- #
@project_status.command(name="display", no_args_is_help=True)
# Options
@project_option(required=True)
# Flags
@click.option(
    "--show-history",
    required=False,
    is_flag=True,
    help="Show history of project statuses in addition to current status.",
)
@click.pass_obj
def display_project_status(click_ctx, project, show_history):
    """Display the status of a specific project.

    Use `--show-history` to see all previous statuses of the project.

    Usable by all user roles.
    """
    try:
        with dds_cli.project_status.ProjectStatusManager(
            project=project,
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as updater:
            updater.get_status(show_history)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds project status release -- #
@project_status.command(name="release", no_args_is_help=True)
# Options
@project_option(required=True)
@click.option(
    "--deadline",
    required=False,
    type=int,
    help="Deadline in days when releasing a project.",
)
@nomail_flag(help_message="Do not send e-mail notifications regarding project updates.")
@click.pass_obj
def release_project(click_ctx, project, deadline, no_mail):
    """Change project status to 'Available'.

    Make project data available for user download. Data cannot be deleted and additional data cannot
    be uploaded. The count-down for when the data access expires starts.

    The `--deadline` option can be used when changing the project status from 'In Progress' to
    'Available' for the first time. In all other cases the deadline option will be ignored.

    Only usable by: Unit Admins / Personnel.
    """
    try:
        with dds_cli.project_status.ProjectStatusManager(
            project=project,
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as updater:
            updater.update_status(new_status="Available", deadline=deadline, no_mail=no_mail)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds project status retract -- #
@project_status.command(name="retract", no_args_is_help=True)
# Options
@project_option(required=True)
@click.pass_obj
def retract_project(click_ctx, project):
    """Change the project status to 'In Progress'.

    'In Progress' is the default status when a project is created. Retracting the project changes
    the status from 'Available' to 'In Progress' again.

    Make project data unavailable to Researchers, and allow Unit Admins / Personnel to upload
    additional data to the project. Data cannot be deleted. Data cannot be overwritten.
    """
    try:
        with dds_cli.project_status.ProjectStatusManager(
            project=project,
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as updater:
            updater.update_status(new_status="In Progress")
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds project status archive -- #
@project_status.command(name="archive", no_args_is_help=True)
# Options
@project_option(required=True)
# Flags
@click.option(
    "--abort",
    required=False,
    is_flag=True,
    default=False,
    help="Something has one wrong in the project.",
)
@click.pass_obj
def archive_project(click_ctx, project: str, abort: bool = False):
    """Change the project status to 'Archived'.

    Certain meta data is kept and it will still be listed in your projects. All data within the
    project is deleted. You cannot revert this change.

    Use the `--abort` flag to indicate that something has gone wrong in the project.
    """
    proceed_deletion = (
        True
        if click_ctx.get("NO_PROMPT", False)
        else dds_cli.utils.get_deletion_confirmation(action="archive", project=project)
    )
    if proceed_deletion:
        try:
            with dds_cli.project_status.ProjectStatusManager(
                project=project,
                no_prompt=click_ctx.get("NO_PROMPT", False),
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as updater:
                updater.update_status(new_status="Archived", is_aborted=abort)
        except (
            dds_cli.exceptions.APIError,
            dds_cli.exceptions.AuthenticationError,
            dds_cli.exceptions.DDSCLIException,
            dds_cli.exceptions.ApiResponseError,
            dds_cli.exceptions.ApiRequestError,
        ) as err:
            LOG.error(err)
            sys.exit(1)


# -- dds project status delete -- #
@project_status.command(name="delete", no_args_is_help=True)
# Options
@project_option(required=True)
@click.pass_obj
def delete_project(click_ctx, project: str):
    """Delete an unreleased project (change project status to 'Deleted').

    Certain meta data is kept (nothing sensitive) and it will still be listed in your projects. All
    data within the project is deleted. You cannot revert this change.
    """
    proceed_deletion = (
        True
        if click_ctx.get("NO_PROMPT", False)
        else dds_cli.utils.get_deletion_confirmation(action="delete", project=project)
    )
    if proceed_deletion:
        try:
            with dds_cli.project_status.ProjectStatusManager(
                project=project,
                no_prompt=click_ctx.get("NO_PROMPT", False),
                token_path=click_ctx.get("TOKEN_PATH"),
            ) as updater:
                updater.update_status(new_status="Deleted")
        except (
            dds_cli.exceptions.APIError,
            dds_cli.exceptions.AuthenticationError,
            dds_cli.exceptions.DDSCLIException,
            dds_cli.exceptions.ApiResponseError,
            dds_cli.exceptions.ApiRequestError,
        ) as err:
            LOG.error(err)
            sys.exit(1)


# -- dds project status busy -- #
@project_status.command(name="busy", no_args_is_help=False)
# Flags
@click.option("--show", required=False, show_default=True, is_flag=True, help="Show busy projects")
@click.pass_obj
def get_busy_projects(click_ctx, show):
    """Returns the number of busy projects.

    Use `--show` to see a list of all busy projects.
    Available to Super Admin only
    """

    try:
        with dds_cli.project_status.ProjectBusyStatusManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as getter:
            getter.get_busy_projects(show=show)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# ACCESS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ ACCESS #
@project_group_command.group(name="access")
@click.pass_obj
def project_access(_):
    """Manage specific users access to a project."""


# -- dds project access grant -- #
@project_access.command(name="grant", no_args_is_help=True)
# Options
@project_option(required=True)
@email_option(help_message="Email of the user you would like to grant access to the project.")
# Flags
@click.option(
    "--owner",
    "owner",
    required=False,
    is_flag=True,
    help=(
        "Grant access as project owner. If not specified, "
        "the user gets Researcher permissions within the project."
    ),
)
@nomail_flag(help_message="Do not send e-mail notifications regarding project updates.")
@click.pass_obj
def grant_project_access(click_ctx, project, email, owner, no_mail):
    """Grant a user access to a project.

    Users can only grant project access to project they themselves have access to, and only to
    users with the role 'Researcher'. To set the Researcher as a Project Owner in this
    specific project, use the `--owner` flag.

    Limited to Unit Admins, Unit Personnel and Researchers set as Project Owners for the project
    in question.
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as granter:
            role = "Researcher"
            if owner:
                role = "Project Owner"
            granter.add_user(email=email, role=role, project=project, no_mail=no_mail)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds project access revoke -- #
@project_access.command(name="revoke", no_args_is_help=True)
# Options
@project_option(required=True)
@email_option(help_message="Email of the user for whom project access is to be revoked.")
@click.pass_obj
def revoke_project_access(click_ctx, project, email):
    """Revoke a users access to a project.

    Users can only revoke project access for users with the role 'Researcher'. To set the Researcher
    as a Project Owner in this specific project, use the `--owner` flag.

    Limited to Unit Admins, Unit Personnel and Researchers set as Project Owners for the project
    in question.
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as revoker:
            revoker.revoke_project_access(project, email)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds project access fix -- #
@project_access.command(name="fix", no_args_is_help=True)
# Positional arguments
@email_arg(required=True)
# Options
@project_option(required=False)
@click.pass_obj
def fix_project_access(click_ctx, email, project):
    """Re-grant project access to user that has lost access due to password reset.

    When a password is reset, all project access is lost. To use the DDS in a meaningful way again,
    the access to the active projects need to be updated.

    Limited to Unit Admins, Unit Personnel and Researchers set as Project Owners for the project
    in question.
    """
    try:
        with dds_cli.account_manager.AccountManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as fixer:
            fixer.fix_project_access(email=email, project=project)
    except (
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


####################################################################################################
####################################################################################################
## DATA #################################################################################### DATA ##
####################################################################################################
####################################################################################################


@dds_main.group(name="data", no_args_is_help=True)
@click.pass_obj
def data_group_command(_):
    """Group command for uploading, downloading and managing project data."""


# ************************************************************************************************ #
# DATA COMMANDS ******************************************************************** DATA COMMANDS #
# ************************************************************************************************ #


# -- dds data put -- #
@data_group_command.command(name="put", no_args_is_help=True)
# Options
@click.option(
    "--mount-dir",
    "-md",
    required=False,
    type=click_pathlib.Path(exists=False, file_okay=False, dir_okay=True, resolve_path=True),
    help=(
        "New directory where the files will be mounted before upload "
        "and any error log files will be saved for a specific upload."
    ),
)
@project_option(required=True, help_message="Project ID to which you're uploading data.")
@source_option(
    help_message="Path to file or directory (local).", option_type=click.Path(exists=True)
)
@source_path_file_option()
@num_threads_option()
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    show_default=True,
    help="Overwrite files if already uploaded.",
)
# Flags
@break_on_fail_flag(help_message="Cancel upload of all files if one fails.")
@silent_flag(
    help_message="Turn off progress bar for each individual file. Summary bars still visible."
)
@click.pass_obj
def put_data(
    click_ctx,
    mount_dir,
    project,
    source,
    source_path_file,
    break_on_fail,
    overwrite,
    num_threads,
    silent,
):
    """Upload data to a project.

    Limited to Unit Admins and Personnel.

    To upload a file (with the same name) a second time, use the `--overwrite` flag.

    Prior to the upload, the DDS checks if the files are compressed and if not compresses them,
    followed by encryption. After this the files are uploaded to the cloud.

    NB! The current setup requires compression and encryption to be performed locally. Make sure you
    have enough space. This will be improved on in future releases.
    The default number of files to compress, encrypt and upload at a time is four. This can be
    changed by altering the `--num-threads` option, but whether or not it works depends on the
    machine you are running the CLI on.

    The token is valid for 7 days. Make sure your token is valid long enough for the
    delivery to finish. To avoid that a delivery fails because of an expired token, we recommend
    reauthenticating yourself before uploading data.
    """
    try:
        dds_cli.data_putter.put(
            mount_dir=mount_dir,
            project=project,
            source=source,
            source_path_file=source_path_file,
            break_on_fail=break_on_fail,
            overwrite=overwrite,
            num_threads=num_threads,
            silent=silent,
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        )
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.UploadError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.NoKeyError,
        dds_cli.exceptions.NoDataError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds data get -- #
@data_group_command.command(name="get", no_args_is_help=True)
# Options
@project_option(required=True, help_message="Project ID from which you're downloading data.")
@num_threads_option()
@source_option(help_message="Path to file or directory.", option_type=str)
@source_path_file_option()
@click.option(
    "--destination",
    "-d",
    required=False,
    type=click_pathlib.Path(exists=False, file_okay=False, dir_okay=True, resolve_path=True),
    multiple=False,
    help="Destination of downloaded files.",
)
# Flags
@break_on_fail_flag(help_message="Cancel download of all files if one fails.")
@silent_flag(
    help_message="Turn off progress bar for each individual file. Summary bars still visible."
)
@click.option(
    "--get-all",
    "-a",
    is_flag=True,
    default=False,
    show_default=True,
    help="Download all project contents.",
)
@click.option(
    "--verify-checksum",
    is_flag=True,
    default=False,
    show_default=True,
    help="Perform SHA-256 checksum verification after download (slower).",
)
@click.pass_obj
def get_data(
    click_ctx,
    project,
    get_all,
    source,
    source_path_file,
    destination,
    break_on_fail,
    num_threads,
    silent,
    verify_checksum,
):
    """Download data from a project.

    To download the data to a specific destination, use the `--destination` option. This cannot be
    an existing directory, for security reasons. This will be improved on in future releases.

    Following to the download, the DDS decrypts the files, checks if the files are compressed and if
    so decompresses them.

    NB! The current setup requires decryption and decompression to be performed locally. Make sure
    you have enough space. This will be improved on in future releases.
    The default number of files to download, decrypt and decompress at a time is four. This can be
    changed by altering the `--num-threads` option, but whether or not it works depends on the
    machine you are running the CLI on.

    The token is valid for 7 days. Make sure your token is valid long enough for the
    delivery to finish. To avoid that a delivery fails because of an expired token, we recommend
    reauthenticating yourself before downloading data.
    """
    if get_all and (source or source_path_file):
        LOG.error(
            "Flag '--get-all' cannot be used together with options '--source'/'--source-path-fail'."
        )
        sys.exit(1)

    try:
        # Begin delivery
        with dds_cli.data_getter.DataGetter(
            project=project,
            get_all=get_all,
            source=source,
            source_path_file=source_path_file,
            break_on_fail=break_on_fail,
            destination=destination,
            silent=silent,
            verify_checksum=verify_checksum,
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as getter:

            with rich.progress.Progress(
                "{task.description}",
                rich.progress.BarColumn(bar_width=None),
                " • ",
                "[progress.percentage]{task.percentage:>3.1f}%",
                refresh_per_second=2,
                console=dds_cli.utils.stderr_console,
            ) as progress:

                # Keep track of futures
                download_threads = {}

                # Iterator to keep track of which files have been handled
                iterator = iter(getter.filehandler.data.copy())

                with concurrent.futures.ThreadPoolExecutor() as texec:
                    task_dwnld = progress.add_task(
                        "Download", total=len(getter.filehandler.data), step="summary"
                    )

                    # Schedule the first num_threads futures for upload
                    for file in itertools.islice(iterator, num_threads):
                        LOG.debug(f"Starting: {rich.markup.escape(str(file))}")
                        # Execute download
                        download_threads[
                            texec.submit(getter.download_and_verify, file=file, progress=progress)
                        ] = file

                    while download_threads:
                        # Wait for the next future to complete
                        ddone, _ = concurrent.futures.wait(
                            download_threads, return_when=concurrent.futures.FIRST_COMPLETED
                        )

                        new_tasks = 0

                        for dfut in ddone:
                            downloaded_file = download_threads.pop(dfut)
                            LOG.debug(
                                f"Future done: {rich.markup.escape(str(downloaded_file))}",
                            )

                            # Get result
                            try:
                                file_downloaded = dfut.result()
                                LOG.debug(
                                    f"Download of {rich.markup.escape(str(downloaded_file))} successful: {file_downloaded}"
                                )
                            except concurrent.futures.BrokenExecutor as err:
                                LOG.critical(
                                    f"Download of file {rich.markup.escape(str(downloaded_file))} failed! Error: {err}"
                                )
                                continue

                            new_tasks += 1
                            progress.advance(task_dwnld)

                        # Schedule the next set of futures for download
                        for next_file in itertools.islice(iterator, new_tasks):
                            LOG.debug(f"Starting: {rich.markup.escape(str(next_file))}")
                            # Execute download
                            download_threads[
                                texec.submit(
                                    getter.download_and_verify,
                                    file=next_file,
                                    progress=progress,
                                )
                            ] = next_file
    except (
        dds_cli.exceptions.InvalidMethodError,
        OSError,
        dds_cli.exceptions.TokenNotFoundError,
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.ApiResponseError,
        SystemExit,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.NoDataError,
        dds_cli.exceptions.DownloadError,
        dds_cli.exceptions.NoKeyError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds data ls -- #
@data_group_command.command(name="ls", no_args_is_help=True)
# Options
@project_option(required=True)
@folder_option(help_message="List contents in this project folder.")
# Flags
@json_flag(help_message="Output in JSON format.")
@size_flag(help_message="Show size of project contents.")
@tree_flag(help_message="Display the entire project(s) directory tree.")
@users_flag(help_message="Display users associated with a project(Requires a project id).")
@click.pass_context
def list_data(ctx, project, folder, json, size, tree, users):
    """List project contents.

    Same as `dds ls --p`.
    """
    ctx.invoke(
        list_projects_and_contents,
        project=project,
        folder=folder,
        size=size,
        tree=tree,
        users=users,
        json=json,
    )


# -- dds data rm -- #
@data_group_command.command(name="rm", no_args_is_help=True)
# Options
@project_option(required=True)
@folder_option(
    help_message="Path to folder to remove.",
    short="-fl",
    multiple=True,
)
@click.option(
    "--file",
    "-f",
    required=False,
    type=str,
    multiple=True,
    help="Path to file to be removed." + dds_cli.utils.multiple_help_text(item="file"),
)
# Flags
@click.option(
    "--rm-all",
    "-a",
    is_flag=True,
    default=False,
    help="Remove all project contents.",
)
@click.pass_obj
def rm_data(click_ctx, project, file, folder, rm_all):
    """Delete data within a specific project.

    Limited to Unit Admins and Personnel.

    Project data can only be deleted if the project has the status 'In Progress' and it has never
    had the status 'Available'.

    This command should be used with caution; once the data is deleted there is no getting it back.
    """
    no_prompt = click_ctx.get("NO_PROMPT", False)

    # Either all or a file
    if rm_all and (file or folder):
        LOG.error("The options '--rm-all' and '--file'/'--folder' cannot be used together.")
        sys.exit(1)

    # Will not delete anything if no file or folder specified
    if project and not any([rm_all, file, folder]):
        LOG.error(
            "One of the options must be specified to perform data deletion: "
            "'--rm-all' / '--file' / '--folder'."
        )
        sys.exit(1)

    # Warn if trying to remove all contents
    if rm_all:
        if no_prompt:
            LOG.warning(f"Deleting all files within project '{project}'")
        else:
            if not rich.prompt.Confirm.ask(
                f"Are you sure you want to delete all files within project '{project}'?"
            ):
                LOG.info("Probably for the best. Exiting.")
                sys.exit(0)

    try:
        with dds_cli.data_remover.DataRemover(
            project=project,
            no_prompt=no_prompt,
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as remover:

            if rm_all:
                remover.remove_all()

            else:
                if file:
                    remover.remove_file(files=file)

                if folder:
                    remover.remove_folder(folder=folder)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.APIError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
    ) as err:
        LOG.error(err)
        sys.exit(1)


####################################################################################################
####################################################################################################
## UNIT #################################################################################### UNIT ##
####################################################################################################
####################################################################################################


@dds_main.group(name="unit", no_args_is_help=True)
@click.pass_obj
def unit_group_command(_):
    """Group command for managing units.

    Limited to Super Admins.
    """


# ************************************************************************************************ #
# UNIT COMMANDS ******************************************************************** UNIT COMMANDS #
# ************************************************************************************************ #

# -- dds unit ls -- #
@unit_group_command.command(name="ls", no_args_is_help=False)
@click.pass_obj
def list_units(click_ctx):
    """List all units and their information."""
    try:
        with dds_cli.unit_manager.UnitManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as lister:
            lister.list_all_units()
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


####################################################################################################
####################################################################################################
## MOTD #################################################################################### MOTD ##
####################################################################################################
####################################################################################################
# Will rethink and discuss the name of the group and command
# Probably need a super admin only group or similar
# For now this is good, just need the functionality


@dds_main.group(name="motd", no_args_is_help=True)
@click.pass_obj
def motd_group_command(_):
    """Group command for managing Message of the Day within DDS.

    Limited to Super Admins.
    """


# ************************************************************************************************ #
# MOTD COMMANDS ******************************************************************** MOTD COMMANDS #
# ************************************************************************************************ #

# -- dds motd add-- #
@motd_group_command.command(name="add", no_args_is_help=True)
@click.argument("message", metavar="[MESSAGE]", nargs=1, type=str, required=True)
@click.pass_obj
def add_new_motd(click_ctx, message):
    """Add a new Message Of The Day.

    Only usable by Super Admins.

    [MESSAGE] is the MOTD that you wish do display to the DDS users.
    """
    try:
        with dds_cli.motd_manager.MotdManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as setter:
            setter.add_new_motd(message)

    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds motd ls -- #
@motd_group_command.command(name="ls", no_args_is_help=False)
@click.pass_obj
def list_active_motds(click_ctx):
    """List all active MOTDs.
    Only usable by Super Admins.
    """
    try:
        with dds_cli.motd_manager.MotdManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as lister:
            lister.list_all_active_motds(table=True)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds motd deactivate -- #
@motd_group_command.command(name="deactivate")
@click.argument("motd_id", metavar="[MOTD_ID]", nargs=1, type=int, required=True)
@click.pass_obj
def deactivate_motd(click_ctx, motd_id):
    """Deactivate Message Of The Day.
    Only usable by Super Admins.
    """
    try:
        with dds_cli.motd_manager.MotdManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as deactivator:
            deactivator.deactivate_motd(motd_id)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


# -- dds motd send -- #
@motd_group_command.command(name="send")
@click.argument("motd_id", metavar="[MOTD_ID]", nargs=1, type=int, required=True)
@click.pass_obj
def send_motd(click_ctx, motd_id):
    """Send motd as email to all users.

    Super Admins only.
    """
    try:
        with dds_cli.motd_manager.MotdManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as sender:
            sender.send_motd(motd_id=motd_id)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
    ) as err:
        LOG.error(err)
        sys.exit(1)


##################################################################################################################
##################################################################################################################
## MAINTENANCE #################################################################################### MAINTENANCE ##
##################################################################################################################
##################################################################################################################


@dds_main.command(name="maintenance", no_args_is_help=True)
@click.argument(
    "setting", metavar="[ON/OFF]", nargs=1, type=click.Choice(["on", "off"], case_sensitive=False)
)
@click.pass_obj
def set_maintenance_mode(click_ctx, setting):
    """Activate / Deactivate Maintenance mode.

    Only usable by Super Admins.
    """
    try:
        with dds_cli.maintenance_manager.MaintenanceManager(
            no_prompt=click_ctx.get("NO_PROMPT", False),
            token_path=click_ctx.get("TOKEN_PATH"),
        ) as setter:
            setter.change_maintenance_mode(setting=setting)
    except (
        dds_cli.exceptions.AuthenticationError,
        dds_cli.exceptions.ApiResponseError,
        dds_cli.exceptions.ApiRequestError,
        dds_cli.exceptions.DDSCLIException,
        dds_cli.exceptions.InvalidMethodError,
    ) as err:
        LOG.error(err)
        sys.exit(1)
