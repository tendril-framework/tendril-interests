

def rewrap_interest(model):
    from tendril import interests
    type_name = model.type
    return interests.type_codes[type_name](model)


def get_interest_stub(interest):
    return {
        'type_name': interest.type_name,
        'name': interest.name,
        'id': interest.id,
        'descriptive_name': interest.descriptive_name
    }