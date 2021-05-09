from inspect import Parameter
from typing import Literal, get_origin, get_args, Any, Union


class JsonToPyFromAnnotationConstructor:
    def __init__(self, annotation: Any, constructor_member_name: str = 'from_json') -> None:
        """ Creates a constructor from type annotations.

        The constructor takes a json object as input and parses it according to the provided
        annotations.

        Args:
            annotation (Any): Type annotation incoming json objects should be parsed as.
            constructor_member_name (str, optional): Alterantive constructor function name for the annoation.
                The ctor will first attempt to parse the object using this function if it exists.
                Defaults to 'from_json'.
        """
        self.annotation = annotation
        self.constructor_member_name = constructor_member_name

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self.construct(*args, **kwds)

    def construct(self, value: Any) -> Any:
        """ Construct the annoation stored in this object from the input value which is a json object.

        Args:
            value (Any): Json object or native value.

        Raises:
            ValueError: Error raised if not constructable.

        Returns:
            Any: Object with type that satisfies the `self.annotation` typing.
        """
        # Parse the special constructor function
        if hasattr(self.annotation, self.constructor_member_name):
            return getattr(self.annotation, self.constructor_member_name)(value)
        # Return by value if no annotation given
        if self.annotation in (Any, Parameter.empty, ...):
            return value
        # Assert type of primitive json values
        # None, str, int, float can be directly parsed by json and can be type checked
        if type(None) is self.annotation:
            if not isinstance(value, self.annotation):
                raise ValueError(value)
            return value
        if self.annotation is str:
            if not isinstance(value, str):
                raise ValueError(value)
            return value
        if self.annotation in (int, float):
            if not isinstance(value, (int, float)):
                raise ValueError(value)
            return value
        origin = get_origin(self.annotation)
        if origin in (tuple, list):
            args = get_args(self.annotation)
            if args[-1] is ...:
                constructor = JsonToPyFromAnnotationConstructor(args[-2])
                return origin(map(constructor.construct, value))
            return origin(
                JsonToPyFromAnnotationConstructor(arg).construct(value[i])
                for i, arg
                in enumerate(args)
            )
        elif origin is dict:
            key_arg, value_arg = get_args(self.annotation)
            key_ctor = JsonToPyFromAnnotationConstructor(key_arg)
            value_ctor = JsonToPyFromAnnotationConstructor(value_arg)
            return {
                key_ctor.construct(key_value): value_ctor.construct(value_value)
                for key_value, value_value
                in value.items()
            }
        elif origin is Union:
            for arg in get_args(self.annotation):
                try:
                    ctor = JsonToPyFromAnnotationConstructor(arg)
                    parsed = ctor.construct(value)
                except Exception:
                    continue
                return parsed
            raise ValueError(value)
        elif origin is Literal:
            for arg in get_args(self.annotation):
                try:
                    parsed = JsonToPyFromAnnotationConstructor(
                        type(arg)).construct(value)
                    if arg != parsed:
                        continue
                    return parsed
                except Exception:
                    pass
            raise ValueError(value)
        return self.annotation(value)
