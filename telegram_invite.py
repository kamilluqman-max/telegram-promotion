import os
import json
import asyncio
from datetime import datetime, timedelta

from telethon import TelegramClient
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

CONTACTS_FILE = "selected_contacts.json"
MESSAGE_FILE = "promotion_message.txt"

# Complete successful-send history.
# Only successful messages are stored here.
SENT_FILE = "sent_contacts.json"

# Campaign history and reporting.
CAMPAIGN_LOG_FILE = "campaign_log.json"


# ============================================================
# FINAL MESSAGING POLICY
# ============================================================

# Number of contacts processed in one batch.
BATCH_SIZE = 2

# Seconds between individual successful/attempted messages.
DELAY_BETWEEN_MESSAGES = 30

# Seconds to wait after each completed batch.
DELAY_BETWEEN_BATCHES = 300

# Maximum successful messages globally per calendar day.
DAILY_SEND_LIMIT = 10

# Maximum successful messages to one contact
# during any rolling 30-day period.
ROLLING_30_DAY_SEND_LIMIT = 2

# Minimum number of full days between successful messages
# to the same contact.
MINIMUM_DAYS_BETWEEN_MESSAGES = 15

# Only contacts with opted_in=True can receive promotions.
REQUIRE_OPT_IN = True


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = TelegramClient(
    "telegram_invite_session",
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
# DATE / TIME HELPERS
# ============================================================

def parse_timestamp(
    timestamp
):

    if not timestamp:

        return None

    try:

        # Supports timestamps such as:
        # 2026-07-25T12:30:00
        # 2026-07-25T12:30:00.123456

        return datetime.fromisoformat(
            timestamp
        )

    except Exception:

        return None


def get_current_date():

    return datetime.now().date().isoformat()


def is_today(
    timestamp
):

    parsed_time = parse_timestamp(
        timestamp
    )

    if not parsed_time:

        return False

    return (
        parsed_time.date()
        ==
        datetime.now().date()
    )


def get_days_since(
    timestamp
):

    parsed_time = parse_timestamp(
        timestamp
    )

    if not parsed_time:

        return None

    return (
        datetime.now()
        -
        parsed_time
    ).total_seconds() / 86400


# ============================================================
# SEND HISTORY FUNCTIONS
# ============================================================

def get_today_successful_sends(
    sent_contacts
):

    count = 0

    for record in sent_contacts:

        sent_at = record.get(
            "sent_at",
            ""
        )

        if is_today(
            sent_at
        ):

            count += 1

    return count


def get_contact_successful_sends(
    sent_contacts,
    contact_id
):

    contact_id = str(
        contact_id
    )

    matching_records = []

    for record in sent_contacts:

        record_id = str(
            record.get(
                "id",
                ""
            )
        )

        if record_id != contact_id:

            continue

        sent_at = record.get(
            "sent_at",
            ""
        )

        parsed_time = parse_timestamp(
            sent_at
        )

        if not parsed_time:

            continue

        matching_records.append(
            {
                "record": record,
                "sent_at": parsed_time
            }
        )

    matching_records.sort(
        key=lambda item: item["sent_at"],
        reverse=True
    )

    return matching_records


def get_rolling_30_day_sends(
    sent_contacts,
    contact_id
):

    contact_id = str(
        contact_id
    )

    cutoff_time = (
        datetime.now()
        -
        timedelta(
            days=30
        )
    )

    count = 0

    matching_records = []

    for record in sent_contacts:

        record_id = str(
            record.get(
                "id",
                ""
            )
        )

        if record_id != contact_id:

            continue

        sent_at = record.get(
            "sent_at",
            ""
        )

        parsed_time = parse_timestamp(
            sent_at
        )

        if not parsed_time:

            continue

        # Only count successful messages
        # inside the rolling 30-day window.

        if parsed_time >= cutoff_time:

            count += 1

            matching_records.append(
                {
                    "record": record,
                    "sent_at": parsed_time
                }
            )

    matching_records.sort(
        key=lambda item: item["sent_at"],
        reverse=True
    )

    return count, matching_records


def get_last_successful_send(
    sent_contacts,
    contact_id
):

    contact_records = (
        get_contact_successful_sends(
            sent_contacts,
            contact_id
        )
    )

    if not contact_records:

        return None

    return contact_records[
        0
    ]


def get_contact_eligibility(
    sent_contacts,
    contact
):

    contact_id = contact.get(
        "id"
    )

    # --------------------------------------------------------
    # Validate contact ID
    # --------------------------------------------------------

    if not contact_id:

        return {

            "eligible": False,

            "reason": (
                "Contact has no valid ID"
            )

        }


    # --------------------------------------------------------
    # Check opt-in status
    # --------------------------------------------------------

    if REQUIRE_OPT_IN:

        if (
            contact.get(
                "opted_in",
                False
            )
            is not True
        ):

            return {

                "eligible": False,

                "reason": (
                    "Contact is not opted in"
                )

            }


    # --------------------------------------------------------
    # Get rolling 30-day send count
    # --------------------------------------------------------

    rolling_30_count, rolling_records = (
        get_rolling_30_day_sends(
            sent_contacts,
            contact_id
        )
    )


    # --------------------------------------------------------
    # Check rolling 30-day limit
    # --------------------------------------------------------

    if (
        rolling_30_count
        >=
        ROLLING_30_DAY_SEND_LIMIT
    ):

        return {

            "eligible": False,

            "reason": (
                "Rolling 30-day message limit reached"
            ),

            "rolling_30_day_count": (
                rolling_30_count
            ),

            "last_sent_at": (
                rolling_records[0][
                    "sent_at"
                ].isoformat()
                if rolling_records
                else None
            )

        }


    # --------------------------------------------------------
    # Find last successful send
    # --------------------------------------------------------

    last_send = (
        get_last_successful_send(
            sent_contacts,
            contact_id
        )
    )


    # --------------------------------------------------------
    # First-time contact
    # --------------------------------------------------------

    if not last_send:

        return {

            "eligible": True,

            "reason": (
                "No previous successful message"
            ),

            "rolling_30_day_count": 0,

            "last_sent_at": None,

            "days_since_last_message": None

        }


    # --------------------------------------------------------
    # Calculate time since last message
    # --------------------------------------------------------

    last_sent_at = last_send[
        "sent_at"
    ]

    days_since_last_message = (
        get_days_since(
            last_sent_at.isoformat()
        )
    )


    # --------------------------------------------------------
    # Check minimum 15-day gap
    # --------------------------------------------------------

    if (
        days_since_last_message
        <
        MINIMUM_DAYS_BETWEEN_MESSAGES
    ):

        return {

            "eligible": False,

            "reason": (
                "Minimum 15-day gap not reached"
            ),

            "rolling_30_day_count": (
                rolling_30_count
            ),

            "last_sent_at": (
                last_sent_at.isoformat()
            ),

            "days_since_last_message": (
                round(
                    days_since_last_message,
                    2
                )
            )

        }


    # --------------------------------------------------------
    # Contact is eligible
    # --------------------------------------------------------

    return {

        "eligible": True,

        "reason": (
            "Contact meets all messaging rules"
        ),

        "rolling_30_day_count": (
            rolling_30_count
        ),

        "last_sent_at": (
            last_sent_at.isoformat()
        ),

        "days_since_last_message": (
            round(
                days_since_last_message,
                2
            )
        )

    }


# ============================================================
# CAMPAIGN LOGGING
# ============================================================

def create_campaign():

    campaign_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return {

        "campaign_id": campaign_id,

        "started_at": (
            datetime.now().isoformat()
        ),

        "finished_at": None,

        "status": "running",

        "daily_send_limit": (
            DAILY_SEND_LIMIT
        ),

        "rolling_30_day_send_limit": (
            ROLLING_30_DAY_SEND_LIMIT
        ),

        "minimum_days_between_messages": (
            MINIMUM_DAYS_BETWEEN_MESSAGES
        ),

        "batch_size": BATCH_SIZE,

        "delay_between_messages": (
            DELAY_BETWEEN_MESSAGES
        ),

        "delay_between_batches": (
            DELAY_BETWEEN_BATCHES
        ),

        "total_contacts": 0,

        "opted_in_contacts": 0,

        "eligible_contacts": 0,

        "successful_sends": 0,

        "failed_sends": 0,

        "skipped_contacts": 0,

        "contacts": []

    }


def save_campaign(
    campaign
):

    campaigns = load_json_file(
        CAMPAIGN_LOG_FILE,
        []
    )

    if not isinstance(
        campaigns,
        list
    ):

        campaigns = []

    campaigns.append(
        campaign
    )

    save_json_file(
        CAMPAIGN_LOG_FILE,
        campaigns
    )


def update_campaign(
    campaign
):

    campaigns = load_json_file(
        CAMPAIGN_LOG_FILE,
        []
    )

    if not isinstance(
        campaigns,
        list
    ):

        campaigns = []

    campaign_id = campaign.get(
        "campaign_id"
    )

    updated = False

    for index, existing_campaign in enumerate(
        campaigns
    ):

        if (
            existing_campaign.get(
                "campaign_id"
            )
            ==
            campaign_id
        ):

            campaigns[index] = campaign

            updated = True

            break

    if not updated:

        campaigns.append(
            campaign
        )

    save_json_file(
        CAMPAIGN_LOG_FILE,
        campaigns
    )


# ============================================================
# CAMPAIGN CONTACT LOG
# ============================================================

def add_campaign_contact_log(
    campaign,
    contact_log
):

    campaign[
        "contacts"
    ].append(
        contact_log
    )

    update_campaign(
        campaign
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    # --------------------------------------------------------
    # CREATE CAMPAIGN
    # --------------------------------------------------------

    campaign = create_campaign()

    save_campaign(
        campaign
    )

    print(
        "\n=========================================="
    )

    print(
        "TELEGRAM PROMOTION CAMPAIGN"
    )

    print(
        "=========================================="
    )

    print(
        f"Campaign ID: "
        f"{campaign['campaign_id']}"
    )

    print(
        f"Daily global limit: "
        f"{DAILY_SEND_LIMIT}"
    )

    print(
        f"Rolling 30-day limit per contact: "
        f"{ROLLING_30_DAY_SEND_LIMIT}"
    )

    print(
        f"Minimum gap between messages: "
        f"{MINIMUM_DAYS_BETWEEN_MESSAGES} days"
    )

    print(
        f"Batch size: "
        f"{BATCH_SIZE}"
    )


    # --------------------------------------------------------
    # LOAD CONTACTS
    # --------------------------------------------------------

    contacts = load_json_file(
        CONTACTS_FILE,
        []
    )

    if not isinstance(
        contacts,
        list
    ):

        contacts = []


    if not contacts:

        print(
            "\nERROR: No contacts found."
        )

        campaign[
            "status"
        ] = "failed"

        campaign[
            "finished_at"
        ] = datetime.now().isoformat()

        update_campaign(
            campaign
        )

        return


    campaign[
        "total_contacts"
    ] = len(
        contacts
    )


    # --------------------------------------------------------
    # LOAD PROMOTION MESSAGE
    # --------------------------------------------------------

    if not os.path.exists(
        MESSAGE_FILE
    ):

        print(
            f"\nERROR: "
            f"{MESSAGE_FILE} not found."
        )

        campaign[
            "status"
        ] = "failed"

        campaign[
            "finished_at"
        ] = datetime.now().isoformat()

        update_campaign(
            campaign
        )

        return


    with open(
        MESSAGE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        message = file.read().strip()


    if not message:

        print(
            "\nERROR: Promotion message is empty."
        )

        campaign[
            "status"
        ] = "failed"

        campaign[
            "finished_at"
        ] = datetime.now().isoformat()

        update_campaign(
            campaign
        )

        return


    # --------------------------------------------------------
    # LOAD SUCCESSFUL SEND HISTORY
    # --------------------------------------------------------

    sent_contacts = load_json_file(
        SENT_FILE,
        []
    )

    if not isinstance(
        sent_contacts,
        list
    ):

        sent_contacts = []


    # --------------------------------------------------------
    # CHECK DAILY GLOBAL LIMIT
    # --------------------------------------------------------

    today_sent_count = (
        get_today_successful_sends(
            sent_contacts
        )
    )

    remaining_daily_capacity = max(

        DAILY_SEND_LIMIT
        -
        today_sent_count,

        0

    )


    print(
        f"\nToday's successful sends: "
        f"{today_sent_count}"
    )

    print(
        f"Remaining daily capacity: "
        f"{remaining_daily_capacity}"
    )


    if remaining_daily_capacity <= 0:

        print(
            "\nDaily sending limit reached."
        )

        print(
            "No messages will be sent today."
        )

        campaign[
            "status"
        ] = "daily_limit_reached"

        campaign[
            "finished_at"
        ] = datetime.now().isoformat()

        update_campaign(
            campaign
        )

        return


    # --------------------------------------------------------
    # CHECK CONTACT ELIGIBILITY
    # --------------------------------------------------------

    eligible_contacts = []

    not_opted_in = 0

    minimum_gap_not_reached = 0

    rolling_limit_reached = 0

    invalid_contacts = 0


    print(
        "\nChecking contact eligibility..."
    )


    for contact in contacts:

        eligibility = (
            get_contact_eligibility(
                sent_contacts,
                contact
            )
        )


        if eligibility[
            "eligible"
        ]:

            eligible_contacts.append(
                contact
            )

            continue


        # ----------------------------------------------------
        # Count skip reasons
        # ----------------------------------------------------

        reason = eligibility.get(
            "reason",
            ""
        )


        if (
            "not opted in"
            in
            reason.lower()
        ):

            not_opted_in += 1


        elif (
            "15-day gap"
            in
            reason.lower()
        ):

            minimum_gap_not_reached += 1


        elif (
            "rolling 30-day"
            in
            reason.lower()
        ):

            rolling_limit_reached += 1


        else:

            invalid_contacts += 1


    campaign[
        "opted_in_contacts"
    ] = len([

        contact

        for contact in contacts

        if contact.get(
            "opted_in",
            False
        )
        is True

    ])


    campaign[
        "eligible_contacts"
    ] = len(
        eligible_contacts
    )


    print(
        "\n=========================================="
    )

    print(
        "CONTACT ELIGIBILITY SUMMARY"
    )

    print(
        "=========================================="
    )

    print(
        f"Total selected contacts: "
        f"{len(contacts)}"
    )

    print(
        f"Opted-in contacts: "
        f"{campaign['opted_in_contacts']}"
    )

    print(
        f"Eligible contacts: "
        f"{len(eligible_contacts)}"
    )

    print(
        f"Not opted in: "
        f"{not_opted_in}"
    )

    print(
        f"15-day gap not reached: "
        f"{minimum_gap_not_reached}"
    )

    print(
        f"Rolling 30-day limit reached: "
        f"{rolling_limit_reached}"
    )

    print(
        f"Invalid contacts: "
        f"{invalid_contacts}"
    )

    print(
        "=========================================="
    )


    # --------------------------------------------------------
    # NO ELIGIBLE CONTACTS
    # --------------------------------------------------------

    if not eligible_contacts:

        print(
            "\nNo contacts are currently eligible."
        )

        campaign[
            "status"
        ] = "no_eligible_contacts"

        campaign[
            "finished_at"
        ] = datetime.now().isoformat()

        update_campaign(
            campaign
        )

        return


    # --------------------------------------------------------
    # LIMIT TO DAILY CAPACITY
    # --------------------------------------------------------

    contacts_to_process = (

        eligible_contacts[
            :remaining_daily_capacity
        ]

    )


    print(
        f"\nContacts selected for today's campaign: "
        f"{len(contacts_to_process)}"
    )


    # --------------------------------------------------------
    # SHOW ACCOUNT
    # --------------------------------------------------------

    me = await client.get_me()


    print(
        "\nTelegram account connected successfully!"
    )


    print(
        f"Name: "
        f"{me.first_name or ''} "
        f"{me.last_name or ''}"
    )


    if me.username:

        print(
            f"Username: "
            f"@{me.username}"
        )


    # --------------------------------------------------------
    # CALCULATE BATCHES
    # --------------------------------------------------------

    total_batches = (

        len(contacts_to_process)
        +
        BATCH_SIZE
        -
        1

    ) // BATCH_SIZE


    print(
        f"\nBatch size: "
        f"{BATCH_SIZE}"
    )


    print(
        f"Total batches today: "
        f"{total_batches}"
    )


    print(
        "\nStarting promotion campaign..."
    )


    # --------------------------------------------------------
    # PROCESS BATCHES
    # --------------------------------------------------------

    for batch_number in range(
        total_batches
    ):

        start = (

            batch_number
            *
            BATCH_SIZE

        )


        end = (

            start
            +
            BATCH_SIZE

        )


        batch = contacts_to_process[
            start:end
        ]


        print(
            f"\n{'=' * 50}"
        )


        print(
            f"Batch "
            f"{batch_number + 1}"
            f"/"
            f"{total_batches}"
        )


        print(
            f"{'=' * 50}"
        )


        for index, contact in enumerate(
            batch
        ):

            name = contact.get(
                "name",
                "Unknown"
            )


            username = contact.get(
                "username"
            )


            contact_id = contact.get(
                "id"
            )


            print(
                f"\nProcessing: "
                f"{name}"
            )


            if username:

                print(
                    f"Username: "
                    f"@{username}"
                )


            # ------------------------------------------------
            # RE-CHECK DAILY LIMIT
            # ------------------------------------------------

            today_sent_count = (
                get_today_successful_sends(
                    sent_contacts
                )
            )


            if (
                today_sent_count
                >=
                DAILY_SEND_LIMIT
            ):

                print(
                    "\nDaily sending limit reached."
                )


                print(
                    "Stopping campaign safely."
                )


                campaign[
                    "status"
                ] = "daily_limit_reached"


                break


            # ------------------------------------------------
            # RE-CHECK CONTACT ELIGIBILITY
            # ------------------------------------------------

            eligibility = (
                get_contact_eligibility(
                    sent_contacts,
                    contact
                )
            )


            if not eligibility[
                "eligible"
            ]:

                print(
                    "SKIPPED: "
                    f"{eligibility['reason']}"
                )


                campaign[
                    "skipped_contacts"
                ] += 1


                add_campaign_contact_log(

                    campaign,

                    {

                        "id": contact_id,

                        "name": name,

                        "username": username,

                        "status": "skipped",

                        "reason": (
                            eligibility[
                                "reason"
                            ]
                        ),

                        "rolling_30_day_count": (

                            eligibility.get(
                                "rolling_30_day_count"
                            )

                        ),

                        "last_sent_at": (

                            eligibility.get(
                                "last_sent_at"
                            )

                        ),

                        "days_since_last_message": (

                            eligibility.get(
                                "days_since_last_message"
                            )

                        ),

                        "processed_at": (

                            datetime.now().isoformat()

                        )

                    }

                )


                continue


            # ------------------------------------------------
            # CREATE CONTACT LOG
            # ------------------------------------------------

            contact_log = {

                "id": contact_id,

                "name": name,

                "username": username,

                "status": "processing",

                "rolling_30_day_count_before": (

                    eligibility.get(
                        "rolling_30_day_count"
                    )

                ),

                "last_sent_at_before": (

                    eligibility.get(
                        "last_sent_at"
                    )

                ),

                "days_since_last_message": (

                    eligibility.get(
                        "days_since_last_message"
                    )

                ),

                "processed_at": (

                    datetime.now().isoformat()

                )

            }


            try:

                # ------------------------------------------------
                # RESOLVE CONTACT
                # ------------------------------------------------

                if not username:

                    print(
                        "SKIPPED: "
                        "No username available."
                    )


                    contact_log[
                        "status"
                    ] = "skipped"


                    contact_log[
                        "reason"
                    ] = (
                        "No username available"
                    )


                    campaign[
                        "skipped_contacts"
                    ] += 1


                    add_campaign_contact_log(

                        campaign,

                        contact_log

                    )


                    continue


                entity = (
                    await client.get_entity(
                        username
                    )
                )


                # ------------------------------------------------
                # SEND MESSAGE
                # ------------------------------------------------

                print(
                    "Sending promotion message..."
                )


                await client.send_message(

                    entity,

                    message

                )


                sent_at = (
                    datetime.now().isoformat()
                )


                # ------------------------------------------------
                # RECORD SUCCESSFUL SEND
                # ------------------------------------------------

                sent_record = {

                    "id": contact_id,

                    "name": name,

                    "username": username,

                    "sent_at": sent_at

                }


                sent_contacts.append(
                    sent_record
                )


                # Save immediately.
                # If the script stops later, this successful
                # send is still recorded.

                save_json_file(

                    SENT_FILE,

                    sent_contacts

                )


                # ------------------------------------------------
                # UPDATE CAMPAIGN LOG
                # ------------------------------------------------

                rolling_count_after, _ = (
                    get_rolling_30_day_sends(

                        sent_contacts,

                        contact_id

                    )
                )


                contact_log[
                    "status"
                ] = "success"


                contact_log[
                    "sent_at"
                ] = sent_at


                contact_log[
                    "rolling_30_day_count_after"
                ] = rolling_count_after


                contact_log[
                    "rolling_30_day_remaining"
                ] = max(

                    ROLLING_30_DAY_SEND_LIMIT
                    -
                    rolling_count_after,

                    0

                )


                campaign[
                    "successful_sends"
                ] += 1


                add_campaign_contact_log(

                    campaign,

                    contact_log

                )


                print(
                    "SUCCESS: "
                    "Message sent."
                )


                print(
                    f"Rolling 30-day sends for contact: "
                    f"{rolling_count_after}/"
                    f"{ROLLING_30_DAY_SEND_LIMIT}"
                )


            except Exception as error:

                error_message = str(
                    error
                )


                print(
                    "ERROR: "
                    f"{error_message}"
                )


                contact_log[
                    "status"
                ] = "failed"


                contact_log[
                    "error"
                ] = error_message


                campaign[
                    "failed_sends"
                ] += 1


                add_campaign_contact_log(

                    campaign,

                    contact_log

                )


                # IMPORTANT:
                # Failed sends are NOT added to sent_contacts.json.
                # Therefore they do not count toward:
                #
                # - Daily successful-send limit
                # - 15-day gap
                # - Rolling 30-day contact limit


            # ------------------------------------------------
            # DELAY BETWEEN MESSAGES
            # ------------------------------------------------

            if (

                index
                <
                len(batch) - 1

            ):

                print(

                    f"\nWaiting "
                    f"{DELAY_BETWEEN_MESSAGES}"
                    f" seconds..."

                )


                await asyncio.sleep(

                    DELAY_BETWEEN_MESSAGES

                )


        # ----------------------------------------------------
        # STOP IF DAILY LIMIT REACHED
        # ----------------------------------------------------

        if campaign[
            "status"
        ] == "daily_limit_reached":

            break


        # ----------------------------------------------------
        # PAUSE BETWEEN BATCHES
        # ----------------------------------------------------

        if (

            batch_number
            <
            total_batches - 1

        ):

            print(
                "\nBatch completed."
            )


            print(

                f"Waiting "
                f"{DELAY_BETWEEN_BATCHES}"
                f" seconds before next batch..."

            )


            await asyncio.sleep(

                DELAY_BETWEEN_BATCHES

            )


    # --------------------------------------------------------
    # FINAL CAMPAIGN STATUS
    # --------------------------------------------------------

    if campaign[
        "status"
    ] == "running":

        if campaign[
            "failed_sends"
        ] > 0:

            campaign[
                "status"
            ] = "completed_with_errors"

        else:

            campaign[
                "status"
            ] = "completed"


    campaign[
        "finished_at"
    ] = datetime.now().isoformat()


    update_campaign(
        campaign
    )


    # --------------------------------------------------------
    # FINAL STATISTICS
    # --------------------------------------------------------

    final_today_count = (
        get_today_successful_sends(
            sent_contacts
        )
    )


    print(
        "\n=========================================="
    )


    print(
        "MESSAGING PROCESS COMPLETED"
    )


    print(
        "=========================================="
    )


    print(
        f"Campaign ID: "
        f"{campaign['campaign_id']}"
    )


    print(
        f"Campaign status: "
        f"{campaign['status']}"
    )


    print(
        f"Successful sends this campaign: "
        f"{campaign['successful_sends']}"
    )


    print(
        f"Failed sends this campaign: "
        f"{campaign['failed_sends']}"
    )


    print(
        f"Skipped contacts: "
        f"{campaign['skipped_contacts']}"
    )


    print(
        f"Total successful sends today: "
        f"{final_today_count}"
    )


    print(
        f"Daily global limit: "
        f"{DAILY_SEND_LIMIT}"
    )


    print(
        f"Rolling 30-day limit per contact: "
        f"{ROLLING_30_DAY_SEND_LIMIT}"
    )


    print(
        f"Minimum gap between messages: "
        f"{MINIMUM_DAYS_BETWEEN_MESSAGES} days"
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