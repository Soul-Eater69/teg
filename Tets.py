def getUnfulfilledCustomers(requests, totalInventory):
    groups = {}

    for customer, quantity, bid, timestamp in requests:
        groups.setdefault(bid, []).append(
            [timestamp, customer, quantity]
        )

    received = set()

    for bid in sorted(groups, reverse=True):
        active = sorted(groups[bid])

        while active and totalInventory > 0:
            next_round = []

            for timestamp, customer, quantity in active:
                if totalInventory == 0:
                    break

                received.add(customer)
                totalInventory -= 1
                quantity -= 1

                if quantity > 0:
                    next_round.append(
                        [timestamp, customer, quantity]
                    )

            active = next_round

        if totalInventory == 0:
            break

    customers = {request[0] for request in requests}
    return sorted(customers - received)
