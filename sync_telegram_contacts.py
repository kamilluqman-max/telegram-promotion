import os
import json
from datetime import datetime

from telethon import TelegramClient, functions
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

# Existing Telegram session
SESSION_NAME = "telegram_invite_session"

# Main campaign contact list
CONTACTS_FILE = "selected_contacts.json"

# Contact sync history
SYNC_LOG_FILE = "contact_sync_log.json"


# ============================================================
# CONTACT FILTER SETTINGS
# ============================================================

# Only contacts with usernames are included.
REQUIRE_USERNAME = True

# Exclude Telegram bots.
EXCLUDE_BOTS = True

# Exclude deleted Telegram accounts.
EXCLUDE_DELETED = True

# New contacts discovered during sync are automatically
# considered opted-in.
#
# IMPORTANT:
# Use this only if your Telegram contact list contains
# people who have permission to receive your promotions.
AUTO_OPT_IN_NEW_CONTACTS = True


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = TelegramClient(
    SESSION_NAME,
    API_ID,
    API_HASH
)


# ============================================================
# FILE FUNCTIONS
# ============================================================

def load_json_file(
    filename,
    default
):

    if not os.path.exists(
        filename
    ):

        return default

    try:

        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(
                file
            )

    except Exception as error:

        print(
            f"WARNING: Could not read "
            f"{filename}: {error}"
        )

        return default


def save_json_file(
    filename,
    data
):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=4
        )


# ============================================================
# CONTACT SYNC LOG
# ============================================================

def create_sync_log():

    return {

        "sync_id": datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        ),

        "started_at": datetime.now().isoformat(),

        "finished_at": None,

        "status": "running",

        "telegram_contacts_found": 0,

        "existing_contacts_before_sync": 0,

        "new_contacts_found": 0,

        "new_contacts_added": 0,

        "duplicates_ignored": 0,

        "excluded_bots": 0,

        "excluded_deleted": 0,

        "excluded_no_username": 0,

        "total_contacts_after_sync": 0,

        "new_contacts": []

    }


def save_sync_log(
    sync_log
):

    logs = load_json_file(
        SYNC_LOG_FILE,
        []
    )

    if not isinstance(
        logs,
        list
    ):

        logs = []

    logs.append(
        sync_log
    )

    save_json_file(
        SYNC_LOG_FILE,
        logs
    )


# ============================================================
# CONTACT HELPERS
# ============================================================

def normalize_username(
    username
):

    if not username:

        return None

    username = str(
        username
    ).strip()

    if username.startswith(
        "@"
    ):

        username = username[1:]

    return username.lower()


def get_contact_id(
    contact
):

    contact_id = contact.get(
        "id"
    )

    if contact_id is None:

        return None

    return str(
        contact_id
    )


def get_contact_key(
    contact
):

    contact_id = get_contact_id(
        contact
    )

    if contact_id:

        return f"id:{contact_id}"

    username = normalize_username(
        contact.get(
            "username"
        )
    )

    if username:

        return f"username:{username}"

    return None


def build_contact_name(
    first_name,
    last_name
):

    first_name = (
        first_name
        or ""
    ).strip()

    last_name = (
        last_name
        or ""
    ).strip()

    return (
        f"{first_name} {last_name}"
    ).strip()


# ============================================================
# MAIN SYNC
# ============================================================

async def main():

    sync_log = create_sync_log()

    # --------------------------------------------------------
    # LOAD EXISTING CONTACTS
    # --------------------------------------------------------

    existing_contacts = load_json_file(
        CONTACTS_FILE,
        []
    )

    if not isinstance(
        existing_contacts,
        list
    ):

        print(
            "WARNING: selected_contacts.json "
            "does not contain a list."
        )

        existing_contacts = []

    sync_log[
        "existing_contacts_before_sync"
    ] = len(
        existing_contacts
    )

    print(
        "\n=========================================="
    )

    print(
        "TELEGRAM CONTACT SYNC"
    )

    print(
        "=========================================="
    )

    print(
        f"Existing campaign contacts: "
        f"{len(existing_contacts)}"
    )


    # --------------------------------------------------------
    # BUILD EXISTING CONTACT INDEXES
    # --------------------------------------------------------

    existing_ids = set()

    existing_usernames = set()

    existing_keys = set()

    for contact in existing_contacts:

        contact_id = get_contact_id(
            contact
        )

        if contact_id:

            existing_ids.add(
                contact_id
            )

        username = normalize_username(
            contact.get(
                "username"
            )
        )

        if username:

            existing_usernames.add(
                username
            )

        contact_key = get_contact_key(
            contact
        )

        if contact_key:

            existing_keys.add(
                contact_key
            )


    # --------------------------------------------------------
    # CONNECT TO TELEGRAM
    # --------------------------------------------------------

    print(
        "\nConnecting to Telegram..."
    )

    me = await client.get_me()

    print(
        "Telegram account connected successfully."
    )

    account_name = build_contact_name(
        getattr(
            me,
            "first_name",
            ""
        ),
        getattr(
            me,
            "last_name",
            ""
        )
    )

    if account_name:

        print(
            f"Name: {account_name}"
        )

    if getattr(
        me,
        "username",
        None
    ):

        print(
            f"Username: "
            f"@{me.username}"
        )


    # --------------------------------------------------------
    # GET TELEGRAM CONTACTS
    # --------------------------------------------------------

    print(
        "\nLoading Telegram contacts..."
    )

    # Telethon does not provide client.get_contacts().
    # We use Telegram's contacts.GetContactsRequest API.

    contacts_result = await client(
        functions.contacts.GetContactsRequest(
            hash=0
        )
    )

    telegram_contacts = (
        contacts_result.users
    )

    sync_log[
        "telegram_contacts_found"
    ] = len(
        telegram_contacts
    )

    print(
        f"Telegram contacts found: "
        f"{len(telegram_contacts)}"
    )


    # --------------------------------------------------------
    # PROCESS CONTACTS
    # --------------------------------------------------------

    new_contacts = []

    for contact in telegram_contacts:

        # ----------------------------------------------------
        # EXCLUDE DELETED ACCOUNTS
        # ----------------------------------------------------

        if (

            EXCLUDE_DELETED

            and

            getattr(
                contact,
                "deleted",
                False
            )

        ):

            sync_log[
                "excluded_deleted"
            ] += 1

            continue


        # ----------------------------------------------------
        # EXCLUDE BOTS
        # ----------------------------------------------------

        if (

            EXCLUDE_BOTS

            and

            getattr(
                contact,
                "bot",
                False
            )

        ):

            sync_log[
                "excluded_bots"
            ] += 1

            continue


        # ----------------------------------------------------
        # GET USERNAME
        # ----------------------------------------------------

        username = normalize_username(

            getattr(
                contact,
                "username",
                None
            )

        )


        # ----------------------------------------------------
        # REQUIRE USERNAME
        # ----------------------------------------------------

        if (

            REQUIRE_USERNAME

            and

            not username

        ):

            sync_log[
                "excluded_no_username"
            ] += 1

            continue


        # ----------------------------------------------------
        # GET CONTACT ID
        # ----------------------------------------------------

        contact_id = getattr(
            contact,
            "id",
            None
        )

        contact_id_string = (

            str(
                contact_id
            )

            if contact_id is not None

            else None

        )


        # ----------------------------------------------------
        # CHECK DUPLICATES BY ID
        # ----------------------------------------------------

        if (

            contact_id_string

            and

            contact_id_string
            in
            existing_ids

        ):

            sync_log[
                "duplicates_ignored"
            ] += 1

            continue


        # ----------------------------------------------------
        # CHECK DUPLICATES BY USERNAME
        # ----------------------------------------------------

        if (

            username

            and

            username
            in
            existing_usernames

        ):

            sync_log[
                "duplicates_ignored"
            ] += 1

            continue


        # ----------------------------------------------------
        # BUILD NEW CONTACT
        # ----------------------------------------------------

        first_name = getattr(
            contact,
            "first_name",
            ""
        )

        last_name = getattr(
            contact,
            "last_name",
            ""
        )

        new_contact = {

            "id": contact_id,

            "name": build_contact_name(
                first_name,
                last_name
            ),

            "username": username,

            "opted_in": (

                True

                if AUTO_OPT_IN_NEW_CONTACTS

                else False

            ),

            "added_at": (
                datetime.now().isoformat()
            ),

            "source": (
                "telegram_contact_sync"
            )

        }


        # ----------------------------------------------------
        # ADD NEW CONTACT
        # ----------------------------------------------------

        new_contacts.append(
            new_contact
        )

        sync_log[
            "new_contacts_found"
        ] += 1


        # ----------------------------------------------------
        # UPDATE INDEXES
        # ----------------------------------------------------

        if contact_id_string:

            existing_ids.add(
                contact_id_string
            )

        if username:

            existing_usernames.add(
                username
            )

        contact_key = get_contact_key(
            new_contact
        )

        if contact_key:

            existing_keys.add(
                contact_key
            )


        # ----------------------------------------------------
        # SAVE NEW CONTACT TO SYNC LOG
        # ----------------------------------------------------

        sync_log[
            "new_contacts"
        ].append({

            "id": contact_id,

            "name": build_contact_name(
                first_name,
                last_name
            ),

            "username": username,

            "opted_in": (
                new_contact[
                    "opted_in"
                ]
            ),

            "status": "added"

        })


    # --------------------------------------------------------
    # ADD NEW CONTACTS TO MAIN CONTACT FILE
    # --------------------------------------------------------

    if new_contacts:

        existing_contacts.extend(
            new_contacts
        )

        save_json_file(

            CONTACTS_FILE,

            existing_contacts

        )

        sync_log[
            "new_contacts_added"
        ] = len(
            new_contacts
        )

    else:

        print(
            "\nNo new eligible contacts found."
        )


    # --------------------------------------------------------
    # FINALIZE SYNC LOG
    # --------------------------------------------------------

    sync_log[
        "total_contacts_after_sync"
    ] = len(
        existing_contacts
    )

    sync_log[
        "finished_at"
    ] = datetime.now().isoformat()

    sync_log[
        "status"
    ] = "completed"


    save_sync_log(
        sync_log
    )


    # --------------------------------------------------------
    # DISPLAY RESULTS
    # --------------------------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "CONTACT SYNC COMPLETED"
    )

    print(
        "=========================================="
    )

    print(
        f"Telegram contacts found: "
        f"{sync_log['telegram_contacts_found']}"
    )

    print(
        f"Existing contacts before sync: "
        f"{sync_log['existing_contacts_before_sync']}"
    )

    print(
        f"New contacts found: "
        f"{sync_log['new_contacts_found']}"
    )

    print(
        f"New contacts added: "
        f"{sync_log['new_contacts_added']}"
    )

    print(
        f"Duplicates ignored: "
        f"{sync_log['duplicates_ignored']}"
    )

    print(
        f"Bots excluded: "
        f"{sync_log['excluded_bots']}"
    )

    print(
        f"Deleted accounts excluded: "
        f"{sync_log['excluded_deleted']}"
    )

    print(
        f"No username excluded: "
        f"{sync_log['excluded_no_username']}"
    )

    print(
        f"Total campaign contacts: "
        f"{sync_log['total_contacts_after_sync']}"
    )

    print(
        "=========================================="
    )


# ============================================================
# START
# ============================================================

with client:

    client.loop.run_until_complete(
        main()
    )