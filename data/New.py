def getUnfulfilledCustomers(
    requests,
    totalInventory
):
    groups = {}

    for customer, quantity, bid, timestamp in requests:
        groups.setdefault(bid, []).append(
            [timestamp, customer, quantity]
        )

    received = set()

    for bid in sorted(groups, reverse=True):
        active = sorted(groups[bid])

        total_requested = sum(
            item[2] for item in active
        )

        customers_served = min(
            totalInventory,
            len(active)
        )

        for i in range(customers_served):
            customer = active[i][1]
            received.add(customer)

        if totalInventory < total_requested:
            totalInventory = 0
            break

        totalInventory -= total_requested

    customers = {
        request[0]
        for request in requests
    }

    return sorted(
        customers - received
    )
